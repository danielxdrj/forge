CREATE TABLE agent_runs (
    id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES tasks (id),
    agent text NOT NULL,
    status text NOT NULL,
    actor text NOT NULL,
    started_at text NOT NULL,
    finished_at text NOT NULL,
    summary text,
    artifacts text NOT NULL,
    pending text NOT NULL,
    logs text NOT NULL,
    usage text,
    cost double precision,
    error text
);
CREATE INDEX agent_runs_task ON agent_runs (task_id);
CREATE TRIGGER agent_runs_no_change BEFORE UPDATE OR DELETE ON agent_runs
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER agent_runs_no_truncate BEFORE TRUNCATE ON agent_runs
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
