-- Consumo de concessão de aprovação (ADR-014). Namespace próprio: chave = approval_grants.id.
-- approval_consumptions (0007) fica intacto: seus grant_id são ids de auditoria antigos e não devem colidir.
CREATE TABLE grant_consumptions (
    grant_id INTEGER PRIMARY KEY REFERENCES approval_grants(id),
    task_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    consumed_by TEXT NOT NULL,
    consumed_at TEXT NOT NULL
);
CREATE TRIGGER grant_consumptions_no_update BEFORE UPDATE ON grant_consumptions BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER grant_consumptions_no_delete BEFORE DELETE ON grant_consumptions BEGIN SELECT RAISE(ABORT, 'append-only'); END;
