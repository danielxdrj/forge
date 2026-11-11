# Forge Core

Núcleo do Forge em Python (ADR-001 monólito modular, ADR-005 configuração fora do Core, ADR-008 linguagem). Sem integrações externas.

## Estrutura
```
pyproject.toml
.env.example
src/forge_core/
  app.py          inicialização (start/main)
  config.py       carga e validação de FORGE_* (falha com mensagem clara)
  logging.py      log JSON com redação de segredos
  errors.py       ForgeError, ConfigError, AutomationDisabledError
  backup.py       backup/restauração do SQLite
  agents/         Orchestrator, executor isolado em container (FRG-6, ADR-013), registro e agente echo (veja agents/README.md)
  projects/       projetos e repositórios gerenciáveis (FRG-5; veja projects/README.md)
  tasks/          gerenciamento de tarefas (FRG-15): model, rules (puras), service (TaskService)
  draft/          rascunho de issue (Cursor CLI + gh local; ADR-015)
  resolver/       implementador local no clone temporário (ADR-016); push/PR só após s/N
  queue/          fila de jobs persistida (SqlJobQueue)
  storage/        persistência (FRG-42)
    repository.py   interface Repository e entidades
    sql.py          SqlRepository (SQLite e PostgreSQL) e open_repository()
    migrate.py      runner de migrações
    migrations/     SQL numerado por dialeto (sqlite/, postgres/)
    drafts.py       helpers de rascunho e task_links (ADR-017; sem UI de tarefas)
    seed.py         semente idempotente dos repos permitidos
  web/            painel FastAPI (extra `[web]`, ADR-017): API JSON de login e tarefas; UI no forge_frontend
  extension/      interfaces: Integration, Agent, contrato de agente (reexporta agents/spec), JobQueue (Job, JobStatus) (implementações: FRG-40 e outras)
tests/core/  conftest (Postgres efêmero), test_projects, test_agents, test_orchestrator, test_task_rules, test_task_service, test_queue, test_core, test_start_automation, test_redact, test_storage
docker-compose.forge.yml  painel local (Postgres 16 + backend JSON + frontend nginx; ADR-017)
docker-compose.dev.yml  Postgres de dev/teste (127.0.0.1:5433; conflita com o padrão do compose.forge)
```

## Variáveis de ambiente
| Nome | Obrigatória | Finalidade |
| --- | --- | --- |
| `FORGE_CONFIG_DIR` | sim | diretório da configuração da empresa (fora do Core) |
| `FORGE_LOG_LEVEL` | não (INFO) | nível de log |
| `FORGE_AUTOMATION_ENABLED` | não (true) | chave global de desligamento das automações |
| `FORGE_DATABASE_URL` | não | `sqlite:///caminho.db` ou `postgresql://...`; sem ela o Core não persiste. A URL nunca é logada |
| `FORGE_DATABASE_MIGRATION_URL` | não | URL do papel dono/migrador. Se definida, `open_repository` migra com ela e a aplicação conecta só com `FORGE_DATABASE_URL` (papel escritor). Nunca logada |
| `FORGE_AGENTS_DISABLED` | não | agentes desativados, separados por vírgula (ex.: `echo`) |
| `FORGE_PG_USER`/`FORGE_PG_PASSWORD`/`FORGE_PG_DB` | só para o compose de dev | credenciais do Postgres local; use valores fora do Git |
| `FORGE_PG_OWNER_PASSWORD` / `FORGE_PG_APP_PASSWORD` / `FORGE_PG_READONLY_PASSWORD` | compose.forge (secrets) | senhas dos três papéis; nunca no Git |
| `FORGE_GITHUB_CLIENT_ID` | para login | client id público do OAuth App (device flow) |
| `FORGE_SESSION_TTL_SECONDS` / `FORGE_COOKIE_SECURE` / `FORGE_WEB_HOSTS` | painel web | prazo da sessão (8 h), flag Secure, allowlist de Host |
| `FORGE_TRUST_FORWARDED` / `FORGE_TRUSTED_PROXIES` | painel web | `X-Forwarded-*` só do proxy listado (compose: `forge_frontend`) |
| `FORGE_CURSOR_AGENT` / `FORGE_CURSOR_MODEL` / `FORGE_GH_BIN` | não | caminhos/opções do rascunho e do resolver; `FORGE_CURSOR_AGENT` é opcional (PATH/`agent.cmd`) |
| `FORGE_RESOLVER_ATTEMPTS` | não | teto de tentativas do motor implementador (1–3, padrão 1) |

Com `FORGE_AUTOMATION_ENABLED=false`, `start()` levanta `AutomationDisabledError` e `main()` sai com código 2. Ausente = ligado.

Nunca coloque segredos aqui; use cofre institucional.

## Executar e testar
```
pip install -e ".[dev,postgres,web]"
FORGE_CONFIG_DIR=<CAMINHO> python -m forge_core.app
pytest
# painel local: docs/operacao/container-local.md — docker compose -f docker-compose.forge.yml up -d --build
```

## Persistência, auditoria e histórico
`open_repository(url)` aplica as migrações pendentes e devolve um `Repository`. Cada `create_task`/`set_task_status` grava tarefa, evento de histórico e auditoria (quem, o quê, quando, alvo, resultado) na mesma transação; título, ator, alvo e resultado passam por `redact()`. Exemplo:
```python
repo = open_repository(settings.database_url)
# API legada de escrita de tarefa está desativada: use TaskService com Principal autenticado (ADR-014)
task = TaskService(repo).create_task("investigar alerta", principal)
repo.task_history(task.id); repo.list_audit()
```
Outros componentes devem chamar `repo.record_audit(actor, action, target, result)` para operações próprias.

### Papéis do PostgreSQL e modelo de ameaça
- **Dono/migrador** (`FORGE_DATABASE_MIGRATION_URL`): cria as tabelas e roda as migrações. Não é usado pela aplicação em produção.
- **Escritor** (`FORGE_DATABASE_URL`): papel sem ser dono, com INSERT/SELECT em `audit_log` e `task_history` e INSERT/SELECT/UPDATE em `tasks`. Provisione com `storage/provisioning/postgres_roles.sql` (opcional, depois das migrações, placeholders `<PAPEL_APP>`, `<SEGREDO_APP>`, `<BANCO>`).
- `audit_log` tem triggers que bloqueiam UPDATE, DELETE (por linha) e TRUNCATE (por statement, migração `0002`), inclusive para o dono.
- **O que o append-only protege:** contra a aplicação (bugs ou código malicioso rodando como escritor) e contra o papel escritor, que nem tem os privilégios.
- **O que NÃO protege:** o dono do banco ou um superuser pode fazer `DROP TRIGGER`, desabilitar triggers, alterar privilégios ou apagar o banco. Proteja essas credenciais, limite quem as tem e mantenha backups fora do banco. Não há garantia criptográfica de imutabilidade nem detecção de adulteração.
- No SQLite não há papéis; a proteção é só por trigger e vale contra a aplicação, não contra quem tem acesso ao arquivo.

### Chaves estrangeiras no SQLite
`PRAGMA foreign_keys = ON` é ativado em toda conexão aberta pelo `SqlRepository`. Comportamento escolhido: apagar uma tarefa que tem histórico **falha** (`IntegrityError`); não existe histórico órfão. O Core não tem operação de apagar tarefa.

### Migrações
Rodam automaticamente em `open_repository`. Para criar uma: adicione `NNNN_descricao.sql` no dialeto afetado (`migrations/sqlite/` e/ou `migrations/postgres/`; a numeração é por dialeto, e o SQLite não tem a 0002 porque não tem TRUNCATE). Nunca edite uma migração já aplicada.

### Backup e restauração
- **SQLite:** `backup_sqlite(db, destino)` e `restore_sqlite(backup, db)` (pare o Forge antes de restaurar). Testado em `test_storage.py`.
- **PostgreSQL (manual, não automatizado):** no compose do painel, `docker compose -f docker-compose.forge.yml exec forge_postgres pg_dump -U forge_owner -d forge -Fc`. Fora dele: `pg_dump -Fc -h 127.0.0.1 -p 5433 -U <USUARIO> <BANCO> > forge.dump` (a 5433 é compartilhada com `docker-compose.dev.yml`). Guarde o dump em local institucional.

## Projetos e repositórios (FRG-5, ADR-012)
`ProjectService` cadastra, lista, edita e desativa projetos e repositórios (migração `0008`, nunca apaga, `settings` validadas) e expõe `resolve_target` para a FRG-21. Veja `projects/README.md`.

## Orquestrador e agentes (FRG-24, ADR-011)
`Orchestrator.dispatch(task_id, principal)` despacha (exige pessoa com papel `editor`) uma tarefa pronta ao agente designado e grava o resultado em `agent_runs`, `task_changes` e `audit_log`. `enqueue(queue, task_id, principal)` grava `dispatch_requests` (migração `0012`) e um job `{dispatch_id, task_id}` — sem token. `job_handler()` revalida papel, sessão e versão. Contrato, ficha, diagrama, exemplo e como adicionar agente: `agents/README.md`. Fronteira: só agentes `read` executam (registro e runtime recusam o resto; aprovação não é autenticação e não libera nada); só o `echo` existe. Reserva atômica de aprovação em `grant_consumptions` (migração `0010`; `approval_consumptions` da `0007` fica como histórico; `0011` copia só o que bate com `approval_grants`). Papéis: o escritor tem SELECT/INSERT em `agent_runs`, `grant_consumptions`, `dispatch_requests` e `approval_consumptions` (append-only, sem DELETE); reprovisione com `postgres_roles.sql`. Limitações: timeout não mata a thread (FRG-6).

## Tarefas (FRG-15, ADR-010)
`TaskService(repo)` gerencia projetos, etapas, tarefas e subtarefas sobre o mesmo banco (migração `0005`). Toda escrita humana recebe um `Principal` autenticado com papel `editor` (ADR-014). Texto como `"pessoa:ana"` é recusado. Em exemplos, `ana` é um Principal obtido por device flow (a CLI faz login por comando; não há arquivo de sessão).
```python
svc = TaskService(repo)
proj = svc.create_project("Forge", ana); etapa = svc.create_stage(proj.id, "Fase 1", ana)
a = svc.create_task("Modelo", ana, stage_id=etapa.id, assignee_kind="agent", assignee_id="dev")
b = svc.create_task("Testes", ana, stage_id=etapa.id)
svc.add_dependency(b.id, a.id, ana)           # b depende de a (obrigatória)
svc.is_ready(b.id)                              # False: a ainda não está done
svc.change_status(b.id, "in_progress", ana)     # TaskRuleError: dependências obrigatórias pendentes
svc.update_task(a.id, ana, expected_version=1, priority="high")
```

## Rascunho de issue (ADR-015)
`python -m forge_core.draft draft --contexto "..."` ou `--arquivo` (stdin: `--arquivo -`). `--retomar <id>` continua sem LLM. `python -m forge_core.draft doctor` diagnostica o adaptador Cursor (nomes de env, nunca valores). `FORGE_CURSOR_MODEL` é obrigatório na geração (escolha da assinatura; sem default de custo). Runbook: `docs/operacao/rascunho-issue.md`.

## Autenticação humana (ADR-014)
`forge_core.auth`: login por OAuth device flow do GitHub (`github.py`), identidades e papéis `owner`/`editor`/`approver` em tabelas append-only (`store.py`) e CLI local (`cli.py`). Pré-requisito humano e operação: `docs/operacao/autenticacao-humana.md`. Os testes usam transporte falso (`tests/core/test_auth.py`).
- **Status:** `planned`, `pending`, `in_progress`, `blocked`, `in_validation`, `done`, `cancelled` (`cancelled` é extra, ADR-010).
  `planned→pending|cancelled`; `pending→in_progress|blocked|cancelled`; `in_progress→blocked|in_validation|cancelled`; `blocked→pending|in_progress|cancelled`; `in_validation→done|in_progress|cancelled`; `done` e `cancelled` são finais.
- **Pronta para execução:** `pending` com todas as dependências obrigatórias `done` (`is_ready`). Entrar em `in_progress` exige isso. Dependência opcional não bloqueia.
- **Conclusão:** só `in_validation→done`, e só com as subtarefas obrigatórias `done`. Exemplo: pai com subtarefa obrigatória `in_progress` → `TaskRuleError`; a opcional pendente não impede.
- **Subtarefa:** `create_task(..., parent_id=pai, required=True|False)`; profundidade 1; herda a etapa. Cancelar o pai não cancela as subtarefas.
- **Responsável:** `assignee_kind` (`person`/`agent`) e `assignee_id`, juntos. O Core não verifica se existem.
- **Datas:** `start_date` na primeira entrada em `in_progress` e `completed_at` em `done` são preenchidas pelo serviço; `due_date` é informada. Atualização por eventos externos é a FRG-17.
- **Concorrência:** `update_task` exige `expected_version`; versão diferente levanta `TaskConflictError` (releia e tente de novo).
- **Ciclos e concorrência:** `add_dependency` valida o ciclo e insere de forma atômica. No PostgreSQL toma `pg_advisory_xact_lock` global do grafo de dependências no início da transação (solta no commit/rollback); no SQLite, `BEGIN IMMEDIATE` já serializa. Escolhido por ser simples e o volume de mudanças no grafo ser baixo; custo: inclusões de dependência esperam umas pelas outras. Alternativas descartadas: SERIALIZABLE com retry (mais complexo) e linha guardiã por projeto (tarefas sem projeto ficariam sem guardião).
- **Histórico:** `svc.changes(id)` (campo, valor antigo e novo, ator, data) e `repo.task_history(id)` (status). Ambos append-only (trigger). Toda mudança e toda recusa vão para `audit_log` (`task.create|update|status|dependency`, `project.create`, `stage.create`), só com nomes de campos e status: o texto da tarefa não entra na auditoria. Não coloque segredos em tarefas.
- **API antiga:** `repo.create_task/set_task_status` recusam qualquer ator (ADR-014). Use `TaskService` com `Principal`.
- **Papéis:** o escritor tem SELECT/INSERT em `task_changes`, `projects`, `stages` e SELECT/INSERT/UPDATE em `task_dependencies`; nenhum DELETE (reprovisione com `postgres_roles.sql`).
- **Troubleshooting:** `TaskRuleError: transição inválida` → veja a tabela acima; `dependências obrigatórias pendentes` → conclua a dependência (uma dependência cancelada não conta como concluída; ajuste-a para opcional ou crie nova tarefa); `TaskConflictError` → releia a tarefa.
- **Limitações:** dependências não podem ser removidas (sem DELETE), apenas alteradas entre obrigatória/opcional; sem edição de projeto/etapa; `done`/`cancelled` não reabrem; sem integração com `jobs` (FRG-24), GitHub (FRG-29) nem eventos (FRG-17).

## Fila de jobs (FRG-40)
`SqlJobQueue(repo, settings=None, max_attempts=5, backoff_base=30, backoff_cap=3600, lease_seconds=300)` usa o mesmo banco e as mesmas migrações (`0003_jobs`). Sem variável de ambiente nova.
```python
q = SqlJobQueue(repo, settings)
q.enqueue("sincronizar", {"ref": "abc"}, actor="gh:1001", idempotency_key="evento-42")  # atribuição no job; autoridade só via Principal no Orchestrator.enqueue
q.run_once(meu_handler, actor="agente:worker")   # claim + handler + complete/fail
```
- **Estados:** `queued` → `running` → `succeeded`; erro volta a `queued` com `run_at` no futuro (backoff) até esgotar `max_attempts`, quando vira `failed` (definitivo). `cancelled` por `cancel()`.
- **Sem duplicidade:** Postgres `FOR UPDATE SKIP LOCKED`; SQLite `BEGIN IMMEDIATE`. Lease vencido (consumidor caiu) devolve o job à fila e conta como tentativa.
- **Entrega pelo menos uma vez:** se o handler cair depois do efeito e antes do `complete`, o job roda de novo. Handlers devem ser idempotentes.
- **Cancelamento:** `queued` cancela na hora; `running` recebe `cancel_requested` e, ao terminar com erro, vira `cancelled` sem retry (cooperativo; handler que conclui com sucesso fica `succeeded`).
- **Automação desligada:** `claim` levanta `AutomationDisabledError`; `enqueue` segue permitido.
- **Fencing:** `claim()` devolve um `Job` com `claim_token` aleatório (só ali; leituras não o expõem). `complete(job_id, actor, claim_token)`, `fail(job_id, error, actor, claim_token)` e `heartbeat(job_id, actor, claim_token)` só valem com o token do claim vigente e com o lease não vencido; senão levantam `JobStateError` e a recusa é auditada (o token nunca é gravado). `heartbeat` renova o lease e só audita recusas. Migração `0004`.
- **Payload:** guardado como veio, nunca vai para auditoria ou logs. Não ponha segredos nele; use referências.
- **Erros do handler:** `run_once` grava em `last_error` e na auditoria só o **tipo** da exceção (ex.: `ValueError`), porque a mensagem pode ecoar o payload. Para registrar uma mensagem, o handler levanta `JobFailure("texto seguro", retryable=True|False)`; ela passa por `redact()`. `fail()` chamado direto também redige o texto, mas quem chama é responsável por não incluir payload.
- **Auditoria:** `job.enqueue`, `job.claim`, `job.complete`, `job.retry`, `job.fail`, `job.cancel`, `job.requeue`, incluindo recusas (`error: ...`).
- **Papéis:** o escritor tem SELECT/INSERT/UPDATE em `jobs` e nenhum DELETE (reprovisione com `postgres_roles.sql` em bancos já provisionados).

### Monitorar e reprocessar
`q.list_jobs("failed")` mostra falhas definitivas (`last_error`, `attempts`); `q.list_jobs("queued")` e `("running")` mostram a fila e o que está preso. Reprocessar: `q.requeue(job_id, actor)` (zera tentativas, audita). SQL equivalente, só leitura: `SELECT id, kind, status, attempts, last_error FROM jobs WHERE status = 'failed'`.

### Postgres de dev/teste
`docker compose -f docker-compose.dev.yml up -d`, `pip install -e ".[dev,postgres]"` e `FORGE_DATABASE_URL=<URL> pytest tests/core`. A URL precisa ser de um papel que possa CREATE DATABASE e CREATE ROLE: os testes criam um banco e um papel escritor efêmeros e os removem no fim. Sem a variável, os testes do Postgres são pulados.

## Troubleshooting
Erro de `psycopg` ausente: `pip install -e ".[postgres]"`. `audit_log é append-only`: a auditoria não aceita UPDATE/DELETE por desenho. Saída `forge-core: Configuração inválida:` lista cada variável faltante ou inválida; corrija e reinicie.

## Limitações e próximos passos
Sem Forge API (framework em aberto), fila (FRG-40), orquestrador (FRG-24). Formato único de configuração: variáveis de ambiente; arquivos da empresa serão lidos de `FORGE_CONFIG_DIR` em etapa futura.

Limitações: a fila é por polling (sem push), sem ordem garantida além de `run_at, id`, sem retenção ou limpeza de jobs concluídos e sem jitter por padrão (parâmetro `jitter`); o Postgres não tem restauração automatizada nem teste de backup automático; sem retenção/arquivamento nem painel de auditoria; `redact()` é por regex e Bearer/Basic mascara até o fim da linha; a auditoria de `start()` ainda não é gravada (o Core não abre o banco na inicialização).

## Isolamento de agentes e reprovisionamento (FRG-6, ADR-013)
O Orchestrator só usa runtime isolado (Docker). Sem Docker, o despacho falha fechado. O reprovisionamento de grants em bancos existentes é manual: `docs/operacao/reprovisionamento-postgres.md`.

O comando `resolver` (ADR-016) **não** passa pelo Orchestrator: é CLI local, escrita só no clone temporário, push/PR pelo Forge após `s`/`N`. Agentes privilegiados do registro continuam bloqueados.
