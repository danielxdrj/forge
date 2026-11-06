CREATE TABLE approval_consumptions (
    grant_id bigint PRIMARY KEY,
    task_id text NOT NULL,
    agent text NOT NULL,
    consumed_by text NOT NULL,
    consumed_at text NOT NULL
);
CREATE TRIGGER approval_consumptions_no_change BEFORE UPDATE OR DELETE ON approval_consumptions
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER approval_consumptions_no_truncate BEFORE TRUNCATE ON approval_consumptions
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
