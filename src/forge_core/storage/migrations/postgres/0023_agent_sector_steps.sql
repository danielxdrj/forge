-- Setor do agente (PLANO_MESTRE, seção 4): a aba Agentes de cada área mostra só os seus.
-- Agentes existentes são de Desenvolvimento.
ALTER TABLE agents ADD COLUMN sector text NOT NULL DEFAULT 'desenvolvimento'
    CHECK (sector IN ('desenvolvimento', 'juridico', 'financeiro'));

-- Passos de cada execução (linha do tempo no detalhe). Append-only, como agent_executions:
-- gravados na mesma transação da execução. A mensagem já chega redigida.
CREATE TABLE agent_execution_events (
    execution_id text NOT NULL REFERENCES agent_executions (id),
    seq integer NOT NULL,
    at text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('step', 'model', 'error')),
    message text NOT NULL DEFAULT '',
    input_tokens bigint,
    output_tokens bigint,
    duration_ms bigint,
    PRIMARY KEY (execution_id, seq)
);
