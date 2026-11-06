# ADR-011: Orquestrador, Agent Runtime e aprovação

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** existir a tarefa de autenticação de aprovadores, a FRG-6 (isolamento) ou a FRG-46 (revisão do ADR-003)

## Contexto
A FRG-24 entrega o Orchestrator e um Agent Runtime mínimo, validados por um agente `echo` sem IA. A FRG-46 e a FRG-47 não estão no repositório; o ADR-003 segue provisório (LLM e motor de execução em aberto).

## Decisões
- **D1, execução:** núcleo síncrono (`Orchestrator.dispatch`) com adaptador para a fila: `Orchestrator.enqueue` e `job_handler()` ligam a `JobQueue` (FRG-40) e reaproveitam retry, lease e cancelamento. Descartados: só síncrono (sem persistência) e só via fila (mais peças).
- **D2, definições de agente:** no código (`AgentSpec`, a "ficha"), registradas em `AgentRegistry`. `FORGE_AGENTS_DISABLED` (lista, opcional) desativa agentes sem mexer no código. Ler definições de arquivo fica como tarefa futura (ADR-005).
- **D3, aprovação humana (política B):** só agentes cujas permissões são exclusivamente `read` despacham direto. Qualquer outra permissão (`write`, `critical`, desconhecida ou vazia) exige `approval.granted` de um ator `pessoa:*`, registrado em `audit_log`, de uso único (`approval.consumed`) e específico do agente e da tarefa. Sem aprovação a recusa é auditada e a tarefa não muda.
- **Fluxo:** automação ligada → tarefa `pending` com dependências obrigatórias concluídas → agente designado (`assignee_kind=agent`), registrado e ativo → aprovação, se exigida → `pending→in_progress` (desempata despachos concorrentes) → execução → `agent_runs` + `task_changes` + auditoria → `in_validation` (sucesso) ou `blocked` (falha, erro, timeout, cancelamento). `done` segue humano.
- **Divisão em subtarefas:** o orquestrador só propõe (`propose_split`); criar exige `apply_split` por uma pessoa.
- **Resultado:** `agent_runs` (append-only, trigger e sem DELETE para o escritor). O resumo do resultado não vai para o `audit_log`, que leva só status, agente e id da execução. Logs, resumo e `usage` passam por `redact()`. Exceção do agente grava só o tipo, salvo `AgentFailure` explícita (redigida).

## Regra obrigatória (autenticação de aprovadores)
A aprovação registra o ator informado e **não autentica quem aprova**. Portanto, **nenhum agente real com permissão `write` ou `critical` pode ser registrado até existir a tarefa de autenticação de aprovadores.** Nesta entrega o único agente registrado é o `echo`, só `read`. A regra é imposta no código: `AgentRegistry.register` recusa agente que exija aprovação; `allow_privileged=True` existe só para testes e deve sair quando a autenticação existir.

## Limites aceitos
- O timeout e o cancelamento são cooperativos e **não matam a thread** do agente; isolamento é a FRG-6.
- Quem tem acesso ao banco como escritor pode inserir linhas no `audit_log`; a aprovação só conta se o ator começar com `pessoa:`, mas isso não é autenticação.
- Aprovação, despacho e atualização de status não formam uma única transação.

## Consequências
Segurança: menor privilégio por padrão (read) e permissão desconhecida exige aprovação. Manutenção: agente novo = registrar uma ficha e uma classe, sem mexer no Orchestrator. Custo: nenhum serviço novo.
