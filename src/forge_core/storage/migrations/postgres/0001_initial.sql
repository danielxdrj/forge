CREATE TABLE tasks (
    id text PRIMARY KEY,
    title text NOT NULL,
    status text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE TABLE task_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id text NOT NULL REFERENCES tasks (id),
    status text NOT NULL,
    actor text NOT NULL,
    at text NOT NULL
);
CREATE TABLE audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at text NOT NULL,
    actor text NOT NULL,
    action text NOT NULL,
    target text NOT NULL,
    result text NOT NULL
);
CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_log é append-only'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
