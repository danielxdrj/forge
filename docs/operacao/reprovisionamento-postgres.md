# Runbook: reprovisionar grants do papel escritor em banco existente

Procedimento administrativo, **não automático**. Use quando um banco já provisionado não tem os grants atuais
(ex.: após FRG-5 ou FRG-24). Não execute em produção sem autorização separada. Referência: ADR-013 (D8).

## Pré-requisitos
- Papel dono/migrador com `FORGE_DATABASE_MIGRATION_URL` (nunca logada). O papel escritor já existe e foi criado
  pelo administrador com `CREATE ROLE` (fora deste procedimento).
- Backup ou snapshot do banco antes da execução.
- Autorização registrada para o ambiente alvo (não substitui esta checagem).

## Pré-checagens manuais (opcional, somente leitura)
```sql
SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = '<PAPEL>';
SELECT count(*) FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = '<PAPEL>');
SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = '<PAPEL>';
```
Todos devem estar vazios ou falsos.

## Execução
```bash
FORGE_DATABASE_MIGRATION_URL=<URL-DO-DONO> python -m forge_core.storage.provisioning.reprovision --role <PAPEL>
```
Saída `{"status": "ok", "checks": [...]}` com código 0, ou `{"status": "error", "error": "<código>"}` com código 1
(ou 2 se a URL não estiver definida). Códigos de erro:

| Código | Significado | Ação |
| --- | --- | --- |
| `role_missing` | papel não existe | criar o papel primeiro |
| `role_privileges_unexpected` | papel com superuser, bypassrls, createdb ou createrole | remover o atributo (fora deste procedimento) |
| `role_membership_unexpected` | papel é membro de outro papel | revisar a herança e remover a membership |
| `role_ownership_unexpected` | papel é dono de tabela ou schema | transferir a propriedade ao dono |
| `default_privileges_unexpected` | default privileges mencionam o papel | revisar `pg_default_acl` |
| `connection_not_owner` | a conexão não é do dono das tabelas | usar `FORGE_DATABASE_MIGRATION_URL` |
| `writer_privilege_unexpected` | escritor tem UPDATE/DELETE/TRUNCATE onde não deve (ex.: PUBLIC) | revogar o privilégio indevido manualmente |
| `writer_grant_missing` | falta SELECT/INSERT esperado | reexecutar após checar o erro |
| `database_error` | erro de banco (detalhe omitido de propósito) | ver o log do servidor |

## Verificação posterior
Reexecutar o comando deve devolver o mesmo conjunto de `checks` (idempotente), e os dados devem permanecer iguais.

## Reversão
Este procedimento só concede grants que estavam previstos em `postgres_roles.sql`. Para reverter um grant específico,
use `REVOKE` manual, com aprovação, registrando a alteração.
