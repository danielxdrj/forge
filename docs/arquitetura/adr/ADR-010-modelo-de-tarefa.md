# ADR-010: Modelo de tarefa, status e responsável

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** a FRG-5 (modelo de projetos) for entregue, ou quando houver cadastro de pessoas e agentes

## Contexto
A FRG-15 precisa de gerenciamento de tarefas com a hierarquia Projeto → Etapa → Tarefa → Subtarefa, dependências e histórico. A FRG-42 já tinha `tasks` e `task_history` mínimas. A FRG-5 ainda não existe.

## Decisões
- **Status (D1):** os seis do padrão de planejamento mais `cancelled`: `planned`, `pending`, `in_progress`, `blocked`, `in_validation`, `done`, `cancelled`. `cancelled` está fora do padrão da empresa porque é preciso abandonar tarefa sem apagar histórico. Transições: planned→pending|cancelled; pending→in_progress|blocked|cancelled; in_progress→blocked|in_validation|cancelled; blocked→pending|in_progress|cancelled; in_validation→done|in_progress|cancelled. `done` e `cancelled` são terminais (reabrir = tarefa nova).
- **Regras:** entrar em `in_progress` exige todas as dependências obrigatórias `done`; "pronta para execução" = `pending` nessa condição. `done` só vem de `in_validation` e exige as subtarefas obrigatórias `done` (a passagem por `in_validation` é a validação da entrega principal). Dependências opcionais e subtarefas opcionais não bloqueiam. Ciclos e auto-dependência são recusados.
- **Responsável (D2):** duas colunas, `assignee_kind` (`person`/`agent`) e `assignee_id`, sempre juntas. O Core valida só formato e tipo; quem existe de fato é assunto da configuração da empresa (ADR-005). Na auditoria o ator continua `pessoa:x` / `agente:x`.
- **Hierarquia (D3, enxuta):** `projects` e `stages` mínimas (id, título, `project_id`); subtarefa é uma tarefa com `parent_task_id` (profundidade máxima 1, herda a etapa). O modelo completo de projeto fica para a FRG-5.
- **Concorrência:** campo `version` (otimista); edição exige `expected_version`.
- **Ciclos:** a inclusão de dependência é atômica com a validação de ciclo, por `pg_advisory_xact_lock` global no PostgreSQL e `BEGIN IMMEDIATE` no SQLite (correção da revisão do PR #21; corrida A→B e B→A reproduzida no Postgres 16).
- **Histórico:** `task_changes` (valor antigo e novo de cada campo) e `task_history` (linha do tempo de status), ambos append-only por trigger (UPDATE, DELETE e TRUNCATE), como `audit_log`.
- **Compatibilidade:** a API antiga do `Repository` (`create_task`, `set_task_status`) continua, sem regras de transição, traduzindo `created`→`pending` e `running`→`in_progress`. A migração `0005` remapeia `tasks` e `task_history` uma única vez, antes dos triggers.

## Consequências
Segurança: o escritor não tem DELETE nas tabelas novas; a auditoria guarda só nomes de campos e status, nunca o texto da tarefa. O texto da tarefa fica como veio: não coloque segredos nele. Limite do append-only: vale contra a aplicação e o escritor, não contra o dono/superuser. Manutenção: se a FRG-5 trouxer outro modelo de projeto, `projects`/`stages` serão revistas.
