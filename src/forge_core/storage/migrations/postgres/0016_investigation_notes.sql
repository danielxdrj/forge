-- Notas manuais por issue (Investigação). Conteúdo só nesta tabela; audit_log guarda id/tamanho.
CREATE TABLE investigation_notes (
    id text PRIMARY KEY,
    issue_key text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    created_by text NOT NULL REFERENCES identities (id),
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE INDEX investigation_notes_issue ON investigation_notes (issue_key, updated_at);
