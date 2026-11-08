# Agentes e Orchestrator (FRG-24, ADR-011)

Stdlib apenas. Nenhuma IA: o provedor ficará atrás de `ProviderAdapter` (só interface, `provider.py`).

## Execução isolada (FRG-6, ADR-013)
- O `Orchestrator` usa `IsolatedRuntime` por padrão (container Docker descartável por execução). Ele **recusa** qualquer outro runtime (`TypeError`).
- Requisito: Docker no host e a imagem `forge-agent-sandbox:prod` (ou `FORGE_AGENT_SANDBOX_IMAGE`). Sem isso, o despacho termina em `error` (`docker_unavailable` ou `sandbox_unavailable`) e **não** executa em thread.
- Perfil do filho: rede negada, raiz somente leitura, sem capacidades, não root, memória, CPU, pids e tmpfs limitados, sem mounts nem variáveis do host.
- Protocolo: o filho recebe id, título e objetivo da tarefa e devolve uma linha JSON validada. Saída fora do formato é `invalid_output`.
- Timeout e cancelamento matam o container (e os descendentes) e confirmam a remoção antes de devolver.
- Limite honesto: o container compartilha o kernel do host. Não é sandbox absoluto.
- Testes: `tests/core` usa um dublê de transporte (`tests/core/inprocess_sandbox.py`), que valida a lógica do Orchestrator mas **não** prova isolamento. A prova real está em `tests/sandbox`, executada no job `sandbox-smoke` do CI com o Docker do runner.

## Fronteira de segurança e limitações reais
- Só agentes `read` executam, e só o `echo` e os agentes de teste existem. Privilegiados e agentes reais continuam bloqueados (registro, runtime e Orchestrator), inclusive em chamadas diretas.
- O registro de aprovação não é autenticação (ADR-011). Para liberar privilegiados: autenticação de aprovadores e nova ADR.
- O container compartilha o kernel do host.
- Efeitos externos do próprio agente só são bloqueados pela rede negada e pelo filesystem somente leitura; o que for escrito no tmpfs some com o container.
- As limitações acima foram aceitas pelo gestor de projetos (ADR-013).

## Reprovisionamento de grants
`python -m forge_core.storage.provisioning.reprovision --role <PAPEL>` (manual, runbook em `docs/operacao/reprovisionamento-postgres.md`).
