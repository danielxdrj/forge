# ADR-011: Orquestrador, Agent Runtime e aprovação

- **Status:** Aprovado (06/11/2026). Atualizado pela ADR-013: o runtime público passou a ser isolado em container; a execução em thread não é mais caminho público.
- **Data:** 2026-11-06
- **Revisar quando:** existir a tarefa de autenticação de aprovadores, a FRG-6 (isolamento) ou a FRG-46 (revisão do ADR-003)

## Contexto
A FRG-24 entrega o Orchestrator e um Agent Runtime mínimo, validados por um agente `echo` sem IA. A FRG-46 e a FRG-47 não estão no repositório; o ADR-003 segue provisório (LLM e motor de execução em aberto).

## Decisões
- **D1, execução:** núcleo síncrono (`Orchestrator.dispatch`) com adaptador para a fila: `Orchestrator.enqueue` e `job_handler()` ligam a `JobQueue` (FRG-40) e reaproveitam retry, lease e cancelamento. Descartados: só síncrono (sem persistência) e só via fila (mais peças).
- **D2, definições de agente:** no código (`AgentSpec`, a "ficha"), registradas em `AgentRegistry`. `FORGE_AGENTS_DISABLED` (lista, opcional) desativa agentes sem mexer no código. Ler definições de arquivo fica como tarefa futura (ADR-005).
- **D3, aprovação humana (política B):** só agentes cujas permissões são exclusivamente `read` despacham. Qualquer outra permissão (`write`, `critical`, desconhecida ou vazia) exige aprovação, e a aprovação registrada **não libera a execução** enquanto não houver autenticação de aprovadores (ver a fronteira de segurança abaixo). O registro de aprovação (`approval.granted`, ator `pessoa:*`) e a reserva atômica existem como contrato.
- **Fluxo:** automação ligada → tarefa `pending` com dependências obrigatórias concluídas → agente designado (`assignee_kind=agent`), registrado e ativo → aprovação, se exigida → `pending→in_progress` (a versão da tarefa desempata despachos concorrentes) → execução → `agent_runs` + `task_changes` + auditoria → `in_validation` (sucesso) ou `blocked` (falha, erro, timeout, cancelamento). `done` segue humano.
- **Divisão em subtarefas:** o orquestrador só propõe (`propose_split`); criar exige `apply_split` por uma pessoa.
- **Resultado:** `agent_runs` (append-only, trigger e sem DELETE para o escritor). O resumo do resultado não vai para o `audit_log`, que leva só status, agente e id da execução. Logs, resumo e `usage` passam por `redact()`. Exceção do agente grava só o tipo, salvo `AgentFailure` explícita (redigida).

## Fronteira de segurança e limitações reais
**Estado atual: apenas agentes `read` executam.** Isto é imposto no código, em três camadas, sem nenhum flag ou construtor que mude o resultado:
1. `AgentRegistry.register` recusa sempre qualquer spec que não seja só `read` ("privileged agents disabled until approver authentication").
2. `AgentRuntime.execute` recusa spec não-`read` mesmo se chamado direto (defesa em profundidade).
3. `Orchestrator.dispatch` usa `approval.decide`, que nunca devolve "executar" para quem exige aprovação: sem aprovação pede aprovação (recusa auditada); com `approval.granted` a recusa auditada passa a ser "privileged agents disabled until approver authentication".

- **O registro de aprovação não é autenticação.** `approval.granted` grava o ator informado; uma identidade `pessoa:qualquer` não autenticada é aceita como texto e **não libera nada**. A exigência do prefixo `pessoa:` filtra agentes honestos, não impede falsificação por quem escreve no banco.
- **Para liberar agentes privilegiados no futuro serão necessárias:** autenticação de aprovadores **e uma nova ADR** que revise esta fronteira. Não basta remover a recusa no código.
- **Reserva atômica da aprovação (contrato futuro):** cada concessão é uma linha do `audit_log` (seu id é o `grant_id`). `ApprovalLedger.reserve` insere o `grant_id` em `approval_consumptions` (chave primária, append-only) numa transação; reservas concorrentes da mesma concessão têm um único vencedor. O consumo vale mesmo que a execução falhe: retry, replay ou novo job exigem **nova aprovação**. Hoje o despacho nunca chega a reservar, porque o privilegiado está desligado; a reserva é testada isoladamente (SQLite e Postgres, com conexões independentes).
- **Gate global em qualquer caminho:** sem `settings`, `dispatch`, `job_handler` e `AgentRuntime` leem o ambiente como o `start()` (`FORGE_AUTOMATION_ENABLED`, `FORGE_AGENTS_DISABLED`); config inválida falha fechada.
- **Timeout e thread:** o agente roda numa thread. Em timeout ou cancelamento o runtime sinaliza `cancel_event`, **sela o contexto** (`log()` vira no-op), descarta qualquer resultado tardio e nada mais é gravado em `agent_runs`, `task_changes` ou `audit_log`. Mas a thread **não é morta**: efeitos externos que ela própria fizer (I/O, rede, arquivos) não podem ser interrompidos sem isolamento (FRG-6). Esse limite é separado da fronteira de autorização: o `echo` só lê e nenhum privilegiado executa.
- **Outros limites:** aprovação, despacho e atualização de status não formam uma única transação; quem escreve no banco como escritor pode inserir linhas no `audit_log`.
- **Atribuição das decisões:** estas limitações foram aceitas pelo gestor de projetos, a quem o usuário delegou as decisões técnicas.

## Consequências
Segurança: menor privilégio por padrão (read); privilegiado desligado até haver autenticação. Manutenção: agente novo = registrar uma ficha e uma classe, sem mexer no Orchestrator. Custo: nenhum serviço novo.
