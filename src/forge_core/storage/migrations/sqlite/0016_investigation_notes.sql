-- Notas manuais por issue (Investigação). Conteúdo só nesta tabela; audit_log guarda id/tamanho.
CREATE TABLE investigation_notes (
    id TEXT PRIMARY KEY,
    issue_key TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES identities (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX investigation_notes_issue ON investigation_notes (issue_key, updated_at);
