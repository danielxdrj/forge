-- Pedido de despacho autorizado por uma pessoa (ADR-014). O job guarda só este id, nunca token.
CREATE TABLE dispatch_requests (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks (id),
    task_version INTEGER NOT NULL,
    identity_id TEXT NOT NULL REFERENCES identities (id),
    requested_at TEXT NOT NULL
);
CREATE TRIGGER dispatch_requests_no_update BEFORE UPDATE ON dispatch_requests BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER dispatch_requests_no_delete BEFORE DELETE ON dispatch_requests BEGIN SELECT RAISE(ABORT, 'append-only'); END;
