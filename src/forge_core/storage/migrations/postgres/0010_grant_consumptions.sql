-- Consumo de concessão de aprovação (ADR-014). Namespace próprio: chave = approval_grants.id.
-- approval_consumptions (0007) fica intacto: seus grant_id são ids de auditoria antigos e não devem colidir.
CREATE TABLE grant_consumptions (
    grant_id bigint PRIMARY KEY REFERENCES approval_grants(id),
    task_id text NOT NULL,
    agent text NOT NULL,
    consumed_by text NOT NULL,
    consumed_at text NOT NULL
);
CREATE TRIGGER grant_consumptions_no_change BEFORE UPDATE OR DELETE ON grant_consumptions
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER grant_consumptions_no_truncate BEFORE TRUNCATE ON grant_consumptions
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
