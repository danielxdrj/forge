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
  queue/          fila de jobs persistida (SqlJobQueue)
  storage/        persistência (FRG-42)
    repository.py   interface Repository e entidades
    sql.py          SqlRepository (SQLite e PostgreSQL) e open_repository()
    migrate.py      runner de migrações
    migrations/     SQL numerado por dialeto (sqlite/, postgres/)
  extension/      interfaces: Integration, Agent, JobQueue (Job, JobStatus) (implementações: FRG-40 e outras)
tests/core/  conftest (Postgres efêmero), test_queue, test_core, test_start_automation, test_redact, test_storage
docker-compose.dev.yml  Postgres de dev/teste (127.0.0.1:5433)
```

## Variáveis de ambiente
| Nome | Obrigatória | Finalidade |
| --- | --- | --- |
| `FORGE_CONFIG_DIR` | sim | diretório da configuração da empresa (fora do Core) |
| `FORGE_LOG_LEVEL` | não (INFO) | nível de log |
| `FORGE_AUTOMATION_ENABLED` | não (true) | chave global de desligamento das automações |
| `FORGE_DATABASE_URL` | não | `sqlite:///caminho.db` ou `postgresql://...`; sem ela o Core não persiste. A URL nunca é logada |
| `FORGE_DATABASE_MIGRATION_URL` | não | URL do papel dono/migrador. Se definida, `open_repository` migra com ela e a aplicação conecta só com `FORGE_DATABASE_URL` (papel escritor). Nunca logada |
| `FORGE_PG_USER`/`FORGE_PG_PASSWORD`/`FORGE_PG_DB` | só para o compose de dev | credenciais do Postgres local; use valores fora do Git |

Com `FORGE_AUTOMATION_ENABLED=false`, `start()` levanta `AutomationDisabledError` e `main()` sai com código 2. Ausente = ligado.

Nunca coloque segredos aqui; use cofre institucional.

## Executar e testar
```
pip install -e ".[dev]"
FORGE_CONFIG_DIR=<CAMINHO> python -m forge_core.app
pytest
```

## Persistência, auditoria e histórico
`open_repository(url)` aplica as migrações pendentes e devolve um `Repository`. Cada `create_task`/`set_task_status` grava tarefa, evento de histórico e auditoria (quem, o quê, quando, alvo, resultado) na mesma transação; título, ator, alvo e resultado passam por `redact()`. Exemplo:
```python
repo = open_repository(settings.database_url)
task = repo.create_task("investigar alerta", actor="agente:triagem")
repo.set_task_status(task.id, "running", actor="pessoa:ana")
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
- **PostgreSQL (manual, não automatizado):** `pg_dump -Fc -h 127.0.0.1 -p 5433 -U <USUARIO> <BANCO> > forge.dump` e `pg_restore --clean -d <BANCO> forge.dump` num banco vazio ou de teste. Guarde o dump em local institucional e restaure em ambiente de teste periodicamente.

## Fila de jobs (FRG-40)
`SqlJobQueue(repo, settings=None, max_attempts=5, backoff_base=30, backoff_cap=3600, lease_seconds=300)` usa o mesmo banco e as mesmas migrações (`0003_jobs`). Sem variável de ambiente nova.
```python
q = SqlJobQueue(repo, settings)
q.enqueue("sincronizar", {"ref": "abc"}, actor="pessoa:ana", idempotency_key="evento-42")
q.run_once(meu_handler, actor="agente:worker")   # claim + handler + complete/fail
```
- **Estados:** `queued` → `running` → `succeeded`; erro volta a `queued` com `run_at` no futuro (backoff) até esgotar `max_attempts`, quando vira `failed` (definitivo). `cancelled` por `cancel()`.
- **Sem duplicidade:** Postgres `FOR UPDATE SKIP LOCKED`; SQLite `BEGIN IMMEDIATE`. Lease vencido (consumidor caiu) devolve o job à fila e conta como tentativa.
- **Entrega pelo menos uma vez:** se o handler cair depois do efeito e antes do `complete`, o job roda de novo. Handlers devem ser idempotentes.
- **Cancelamento:** `queued` cancela na hora; `running` recebe `cancel_requested` e, ao terminar com erro, vira `cancelled` sem retry (cooperativo; handler que conclui com sucesso fica `succeeded`).
- **Automação desligada:** `claim` levanta `AutomationDisabledError`; `enqueue` segue permitido.
- **Payload:** guardado como veio, nunca vai para auditoria ou logs. Não ponha segredos nele; use referências. `last_error` passa por `redact()`.
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
