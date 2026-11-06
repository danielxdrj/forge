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
  storage/        persistência (FRG-42)
    repository.py   interface Repository e entidades
    sql.py          SqlRepository (SQLite e PostgreSQL) e open_repository()
    migrate.py      runner de migrações
    migrations/     SQL numerado por dialeto (sqlite/, postgres/)
  extension/      interfaces: Integration, Agent, TaskQueue (implementações: FRG-40 e outras)
tests/core/  test_core, test_start_automation, test_redact, test_storage
docker-compose.dev.yml  Postgres de dev/teste (127.0.0.1:5433)
```

## Variáveis de ambiente
| Nome | Obrigatória | Finalidade |
| --- | --- | --- |
| `FORGE_CONFIG_DIR` | sim | diretório da configuração da empresa (fora do Core) |
| `FORGE_LOG_LEVEL` | não (INFO) | nível de log |
| `FORGE_AUTOMATION_ENABLED` | não (true) | chave global de desligamento das automações |
| `FORGE_DATABASE_URL` | não | `sqlite:///caminho.db` ou `postgresql://...`; sem ela o Core não persiste. A URL nunca é logada |
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

### Migrações
Rodam automaticamente em `open_repository`. Para criar uma: adicione `NNNN_descricao.sql` em `migrations/sqlite/` e `migrations/postgres/`. Nunca edite uma migração já aplicada.

### Backup e restauração
- **SQLite:** `backup_sqlite(db, destino)` e `restore_sqlite(backup, db)` (pare o Forge antes de restaurar). Testado em `test_storage.py`.
- **PostgreSQL (manual, não automatizado):** `pg_dump -Fc -h 127.0.0.1 -p 5433 -U <USUARIO> <BANCO> > forge.dump` e `pg_restore --clean -d <BANCO> forge.dump` num banco vazio ou de teste. Guarde o dump em local institucional e restaure em ambiente de teste periodicamente.

### Postgres de dev/teste
`docker compose -f docker-compose.dev.yml up -d`, `pip install -e ".[dev,postgres]"` e `FORGE_DATABASE_URL=<URL> pytest tests/core`. Sem a variável, os testes do Postgres são pulados.

## Troubleshooting
Erro de `psycopg` ausente: `pip install -e ".[postgres]"`. `audit_log é append-only`: a auditoria não aceita UPDATE/DELETE por desenho. Saída `forge-core: Configuração inválida:` lista cada variável faltante ou inválida; corrija e reinicie.

## Limitações e próximos passos
Sem Forge API (framework em aberto), fila (FRG-40), orquestrador (FRG-24). Formato único de configuração: variáveis de ambiente; arquivos da empresa serão lidos de `FORGE_CONFIG_DIR` em etapa futura.

Limitações: o Postgres não tem restauração automatizada nem teste de backup automático; sem retenção/arquivamento nem painel de auditoria; `redact()` é por regex e Bearer/Basic mascara até o fim da linha; a auditoria de `start()` ainda não é gravada (o Core não abre o banco na inicialização).
