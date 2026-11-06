-- Provisionamento OPCIONAL de papéis do PostgreSQL (execute como dono/superuser, DEPOIS das migrações).
-- Substitua os placeholders; o valor do segredo fica fora do Git.
--   <PAPEL_APP>   papel escritor usado em FORGE_DATABASE_URL
--   <SEGREDO_APP> senha do papel escritor
--   <BANCO>       nome do banco
-- O dono/migrador (FORGE_DATABASE_MIGRATION_URL) é quem cria as tabelas e continua dono delas.
CREATE ROLE <PAPEL_APP> LOGIN PASSWORD '<SEGREDO_APP>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE <BANCO> TO <PAPEL_APP>;
GRANT USAGE ON SCHEMA public TO <PAPEL_APP>;
GRANT SELECT, INSERT ON audit_log, task_history, task_changes, stages, agent_runs, approval_consumptions TO <PAPEL_APP>;
GRANT SELECT, INSERT, UPDATE ON tasks, jobs, task_dependencies, projects, repositories TO <PAPEL_APP>;
GRANT SELECT ON schema_migrations TO <PAPEL_APP>;
-- Sem DELETE em nenhuma tabela: projeto e repositório são desativados (active=0), nunca apagados.
-- Sem UPDATE/DELETE/TRUNCATE em audit_log e sem ser dono de nenhuma tabela.
