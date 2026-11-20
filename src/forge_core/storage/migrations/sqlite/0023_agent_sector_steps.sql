-- Setor do agente (PLANO_MESTRE, seção 4): a aba Agentes de cada área mostra só os seus.
-- Agentes existentes são de Desenvolvimento.
ALTER TABLE agents ADD COLUMN sector TEXT NOT NULL DEFAULT 'desenvolvimento'
    CHECK (sector IN ('desenvolvimento', 'juridico', 'financeiro'));

-- Passos de cada execução (linha do tempo no detalhe). Append-only, como agent_executions:
-- gravados na mesma transação da execução. A mensagem já chega redigida.
CREATE TABLE agent_execution_events (
    execution_id TEXT NOT NULL REFERENCES agent_executions (id),
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('step', 'model', 'error')),
    message TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    PRIMARY KEY (execution_id, seq)
);
