CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks (id),
    agent TEXT NOT NULL,
    status TEXT NOT NULL,
    actor TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    summary TEXT,
    artifacts TEXT NOT NULL,
    pending TEXT NOT NULL,
    logs TEXT NOT NULL,
    usage TEXT,
    cost REAL,
    error TEXT
);
CREATE INDEX agent_runs_task ON agent_runs (task_id);
CREATE TRIGGER agent_runs_no_update BEFORE UPDATE ON agent_runs
BEGIN SELECT RAISE(ABORT, 'agent_runs é append-only'); END;
CREATE TRIGGER agent_runs_no_delete BEFORE DELETE ON agent_runs
BEGIN SELECT RAISE(ABORT, 'agent_runs é append-only'); END;
