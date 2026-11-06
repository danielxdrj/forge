# ADR-004: Tecnologia de persistência

- **Status:** Aprovado com ajuste (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** a stack for definida ou o volume/concorrência mudar

## Contexto
Armazenar tarefas, estados, aprovações, resultados e auditoria. O banco não foi decidido; o legado usa PostgreSQL, mas não deve orientar a escolha (FRG-9).

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| PostgreSQL | Robusto, concorrência, backup e ferramentas conhecidos; serve a auditoria | Serviço a operar, credenciais, backup |
| SQLite | Zero operação, um arquivo | Concorrência limitada; backup e acesso remoto manuais; migração futura |
| Arquivos (JSON/Markdown) no Git | Transparente, versionado | Sem consulta nem integridade; ruim para estado e auditoria |

## Recomendação
PostgreSQL, atrás de uma interface de repositório e com migrações versionadas desde o início. Justificativa: estado e auditoria exigem integridade e múltiplos processos (API + execuções). **[Opinião]** SQLite é aceitável para o primeiro protótipo se o responsável preferir menos operação.

## Consequências
Manutenção: média (backup, migração). Segurança: segredo do banco fora do Git, usuário com menor privilégio; auditoria sem permissão de update/delete. Custo: baixo.

## Ajuste aprovado
PostgreSQL é o alvo; SQLite só entra no protótipo. A FRG-42 ainda compara alternativas. O acesso aos dados passa por uma camada de repositório. O banco do legado não define a escolha.

## Decisão FRG-42 (06/11/2026)
- **Armazenamento:** PostgreSQL (driver `psycopg`, extra opcional `[postgres]`) atrás da interface `Repository`. SQLite da stdlib é o adaptador de testes e protótipo. Os testes do Postgres só rodam com `FORGE_DATABASE_URL` definida.
- **Migrações:** runner próprio (`storage/migrate.py`), SQL numerado por dialeto e tabela `schema_migrations`. Sem Alembic nem SQLAlchemy.
- **Auditoria:** `audit_log` é append-only (trigger bloqueia UPDATE/DELETE nos dois bancos). Em produção, o usuário da aplicação deve ter só INSERT/SELECT.
- **Compose:** `docker-compose.dev.yml` sobe só o Postgres do Forge novo, em `127.0.0.1:5433`.
