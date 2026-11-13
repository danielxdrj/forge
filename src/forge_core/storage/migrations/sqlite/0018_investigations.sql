-- Investigação livre (sem issue obrigatória): reaproveita investigation_notes.
-- SQLite não altera NOT NULL de uma coluna existente: reconstrói a tabela.
CREATE TABLE investigation_notes_new (
    id TEXT PRIMARY KEY,
    issue_key TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES identities (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'note',
    repos_json TEXT NOT NULL DEFAULT '[]',
    connection_ids_json TEXT NOT NULL DEFAULT '[]',
    engine TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT ''
);
INSERT INTO investigation_notes_new (id, issue_key, title, body, created_by, created_at, updated_at)
SELECT id, issue_key, title, body, created_by, created_at, updated_at FROM investigation_notes;
DROP TABLE investigation_notes;
ALTER TABLE investigation_notes_new RENAME TO investigation_notes;
CREATE INDEX investigation_notes_issue ON investigation_notes (issue_key, updated_at);
CREATE INDEX investigation_notes_kind ON investigation_notes (kind, updated_at);
