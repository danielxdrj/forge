# ADR-013: Isolamento de agentes (executor em container) e reprovisionamento de grants

- **Status:** Aprovado (08/11/2026), por decisão do gestor de projetos (aprovação de container por execução com o perfil restrito abaixo)
- **Data:** 2026-11-08
- **Revisar quando:** for aprovado um agente real (FRG-43+), houver autenticação de aprovadores (ADR-011), ou o kernel compartilhado virar requisito de isolamento mais forte

## Contexto
A FRG-24 (ADR-011) executava agentes em thread. A FRG-6 exige execução isolada: filesystem, rede, credenciais e recursos limitados. A aprovação do gestor cobre um container por execução, com o perfil restrito abaixo, e apenas para agentes `read` de teste. Agentes reais e privilegiados continuam bloqueados.

## Decisões
- **D1, mecanismo:** container Docker descartável por execução, lançado pelo supervisor (processo do Forge) via `docker` CLI. O daemon nunca é exposto ao filho (sem socket). Descartado: user namespaces sem container (outro mecanismo, não aprovado), e thread (não isola).
- **D2, perfil do filho:** `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, usuário não root (65532), `--memory 128m --memory-swap 128m`, `--cpus 0.5`, `--pids-limit 32`, `fsize` de 16 MiB, `/tmp` em tmpfs de 16 MiB `noexec,nosuid`, sem mounts, sem `--env` do host (só o payload pela entrada padrão). Imagem fixa por digest, construída antes da execução (`deploy/sandbox/Dockerfile`). Nenhum download durante a execução.
- **D3, integração:** `IsolatedRuntime` é o runtime do `Orchestrator`. O padrão (`default_runtime`) usa Docker (`FORGE_AGENT_SANDBOX_IMAGE`, opcional). O Orchestrator **recusa** qualquer runtime que não seja isolado (`TypeError`). Não há segundo registro, scheduler ou runtime: o fluxo de despacho, a auditoria e `agent_runs` são os existentes.
- **D4, falha fechada sem fallback:** sem Docker, imagem ausente ou isolamento não configurado, o despacho termina em `error` (`docker_unavailable`, `sandbox_unavailable`) e não executa em thread. Não há provisionamento automático de Docker em produção.
- **D5, protocolo:** o filho recebe `{agent, payload}` (id, título e objetivo da tarefa) e devolve **uma** linha JSON validada (até 64 KiB; `status`, `summary` até 2000, `logs` até 50 linhas de 300, `usage`, `cost`). Saída fora do formato vira `invalid_output`. Nada é desserializado como código.
- **D6, timeout e cancelamento:** o supervisor mata o container (`docker kill`, o que encerra os descendentes por pid namespace), remove com `docker rm -f` e **confirma a remoção** antes de devolver. Se não confirmar: `cleanup_unconfirmed`. Não há estado aceito sem confirmação.
- **D7, escrita:** o filho nunca fala com o banco nem com a auditoria. O pai grava `agent_runs`, transições e `audit_log`. Erros voltam só com código fixo; texto do agente passa por `redact()`.
- **D8, reprovisionamento:** `forge_core.storage.provisioning.reprovision` reaproveita `postgres_roles.sql` sem a linha `CREATE ROLE`. Pré-checagens (atributos, membership, dono de tabela/schema, default privileges, conexão do dono) e pós-checagens (escritor sem DELETE/TRUNCATE/UPDATE em tabelas append-only). Não revoga acesso alheio: falha sanitizada e o administrador decide. Só executa manualmente, nunca no startup (runbook em `docs/operacao/reprovisionamento-postgres.md`).

## Perfil de ameaça e limites reais (aceitos pelo gestor de projetos)
- **O container compartilha o kernel do host.** Isso reduz a superfície, não é sandbox absoluto: uma falha no kernel ou no runtime afeta o host. Não tratamos o container como fronteira de segurança forte para código arbitrário.
- **Os controles são verificados no runner de CI** (Docker real do `ubuntu-latest`), pelo job `sandbox-smoke`. Os testes locais sem Docker usam um dublê de transporte (`tests/core/inprocess_sandbox.py`) só para validar a lógica do Orchestrator; eles **não** provam isolamento.
- **Limites de recurso são aplicados pelo runtime do container**, e o teste de memória mede o limite em um filho, para não derrubar o agente.
- **Efeitos externos do agente:** só existe rede negada; o que o agente escrever dentro do próprio container some com ele.
- **Privilegiados e reais:** continuam bloqueados (`AgentRegistry.register`, `AgentRuntime` e `Orchestrator`). Liberar agentes privilegiados exige autenticação de aprovadores e nova ADR (ADR-011).
- **Docker é requisito do caminho aprovado.** Hosts sem Docker recusam o despacho. Não instalamos nem elevamos privilégios para obtê-lo.
- **Imagem base fixada por digest** (`python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54`, índice multi-arquitetura obtido do Docker Hub em 08/11/2026). Atualizar exige novo digest revisado, no Dockerfile e aqui, com o CI verde.
- **Pendências:** decidir se a produção usa só o executor (hoje é o padrão); decidir o provisionamento de Docker em produção.

## Consequências
Agentes read de teste executam isolados e com rastreio; a mudança de mecanismo fica restrita ao runtime, sem novo registro. O custo é exigir Docker no caminho público e manter uma imagem.
