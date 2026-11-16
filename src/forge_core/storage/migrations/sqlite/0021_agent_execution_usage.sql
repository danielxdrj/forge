-- Uso do motor por execução de agente (aba Agentes → detalhe). Vem do JSON do `claude -p`:
-- tokens de entrada, saída e cache, turnos, modelo e custo estimado a preço de lista da API.
-- Execuções antigas e motores que não informam uso ficam com NULL ("sem dado" na tela).
ALTER TABLE agent_executions ADD COLUMN input_tokens INTEGER;
ALTER TABLE agent_executions ADD COLUMN output_tokens INTEGER;
ALTER TABLE agent_executions ADD COLUMN cache_read_tokens INTEGER;
ALTER TABLE agent_executions ADD COLUMN cache_write_tokens INTEGER;
ALTER TABLE agent_executions ADD COLUMN turns INTEGER;
ALTER TABLE agent_executions ADD COLUMN model TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_executions ADD COLUMN cost_usd REAL;
