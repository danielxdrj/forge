-- Uso do motor por execução de agente (aba Agentes → detalhe). Vem do JSON do `claude -p`:
-- tokens de entrada, saída e cache, turnos, modelo e custo estimado a preço de lista da API.
-- Execuções antigas e motores que não informam uso ficam com NULL ("sem dado" na tela).
ALTER TABLE agent_executions ADD COLUMN input_tokens bigint;
ALTER TABLE agent_executions ADD COLUMN output_tokens bigint;
ALTER TABLE agent_executions ADD COLUMN cache_read_tokens bigint;
ALTER TABLE agent_executions ADD COLUMN cache_write_tokens bigint;
ALTER TABLE agent_executions ADD COLUMN turns integer;
ALTER TABLE agent_executions ADD COLUMN model text NOT NULL DEFAULT '';
ALTER TABLE agent_executions ADD COLUMN cost_usd double precision;
