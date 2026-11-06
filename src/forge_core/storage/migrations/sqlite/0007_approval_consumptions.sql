CREATE TABLE approval_consumptions (
    grant_id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    consumed_by TEXT NOT NULL,
    consumed_at TEXT NOT NULL
);
CREATE TRIGGER approval_consumptions_no_update BEFORE UPDATE ON approval_consumptions
BEGIN SELECT RAISE(ABORT, 'approval_consumptions é append-only'); END;
CREATE TRIGGER approval_consumptions_no_delete BEFORE DELETE ON approval_consumptions
BEGIN SELECT RAISE(ABORT, 'approval_consumptions é append-only'); END;
