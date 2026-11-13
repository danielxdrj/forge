-- Governança da aba "Agentes" (catálogo/monitoramento). Distinto do Orchestrator interno
-- (agent_runs/approval_grants/approval_consumptions, migrações 0006/0007/0010): aqui não há
-- execução, só cadastro, métricas e aprovação de escrita. Nomes de tabela não colidem.
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL CHECK (scope IN ('development', 'company_system')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'error')),
    trigger TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT '',
    permissions_read TEXT NOT NULL DEFAULT '[]',
    permissions_write TEXT NOT NULL DEFAULT '[]',
    permissions_denied TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE agent_executions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents (id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error', 'running')),
    event TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER,
    log TEXT NOT NULL DEFAULT ''
);
CREATE INDEX agent_executions_agent ON agent_executions (agent_id, started_at);
CREATE TABLE agent_approvals (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents (id),
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT REFERENCES identities (id)
);
CREATE INDEX agent_approvals_agent ON agent_approvals (agent_id, status);
