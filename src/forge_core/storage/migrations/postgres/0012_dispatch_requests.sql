-- Pedido de despacho autorizado por uma pessoa (ADR-014). O job guarda só este id, nunca token.
CREATE TABLE dispatch_requests (
    id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES tasks (id),
    task_version bigint NOT NULL,
    identity_id text NOT NULL REFERENCES identities (id),
    requested_at text NOT NULL
);
CREATE TRIGGER dispatch_requests_no_change BEFORE UPDATE OR DELETE ON dispatch_requests
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER dispatch_requests_no_truncate BEFORE TRUNCATE ON dispatch_requests
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
