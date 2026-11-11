-- Renovação deslizante de sessão: append-only, sem UPDATE em sessions.
CREATE TABLE session_renewals (
    id text PRIMARY KEY,
    session_id text NOT NULL REFERENCES sessions(id),
    expires_at text NOT NULL,
    at text NOT NULL
);
CREATE INDEX session_renewals_session ON session_renewals (session_id);
CREATE TRIGGER session_renewals_no_change BEFORE UPDATE OR DELETE ON session_renewals
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER session_renewals_no_truncate BEFORE TRUNCATE ON session_renewals
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
