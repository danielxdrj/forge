-- Governança da aba "Agentes" (catálogo/monitoramento). Distinto do Orchestrator interno
-- (agent_runs/approval_grants/approval_consumptions, migrações 0006/0007/0010): aqui não há
-- execução, só cadastro, métricas e aprovação de escrita. Nomes de tabela não colidem.
CREATE TABLE agents (
    id text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    scope text NOT NULL CHECK (scope IN ('development', 'company_system')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'error')),
    trigger text NOT NULL DEFAULT '',
    engine text NOT NULL DEFAULT '',
    permissions_read text NOT NULL DEFAULT '[]',
    permissions_write text NOT NULL DEFAULT '[]',
    permissions_denied text NOT NULL DEFAULT '[]',
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE TABLE agent_executions (
    id text PRIMARY KEY,
    agent_id text NOT NULL REFERENCES agents (id),
    started_at text NOT NULL,
    finished_at text,
    status text NOT NULL CHECK (status IN ('ok', 'error', 'running')),
    event text NOT NULL DEFAULT '',
    duration_ms bigint,
    log text NOT NULL DEFAULT ''
);
CREATE INDEX agent_executions_agent ON agent_executions (agent_id, started_at);
CREATE TABLE agent_approvals (
    id text PRIMARY KEY,
    agent_id text NOT NULL REFERENCES agents (id),
    action text NOT NULL,
    details text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at text NOT NULL,
    decided_at text,
    decided_by text REFERENCES identities (id)
);
CREATE INDEX agent_approvals_agent ON agent_approvals (agent_id, status);
