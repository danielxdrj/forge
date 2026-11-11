-- Rascunhos e vínculos de tarefa (PR A / ADR-017). Sessão web ganha expires_at; CLI legado permanece NULL.
CREATE TABLE drafts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks (id),
    repo TEXT NOT NULL,
    body_md TEXT NOT NULL,
    tipo TEXT NOT NULL,
    prioridade TEXT NOT NULL,
    size TEXT NOT NULL,
    preview_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('rascunho', 'confirmado', 'publicado', 'cancelado')),
    created_by TEXT NOT NULL REFERENCES identities (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX drafts_task ON drafts (task_id);
CREATE TABLE task_links (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks (id),
    kind TEXT NOT NULL CHECK (kind IN ('issue', 'pr', 'branch')),
    repo TEXT NOT NULL,
    number INTEGER,
    url TEXT NOT NULL,
    board_item_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (task_id, kind, url)
);
CREATE INDEX task_links_task ON task_links (task_id);
ALTER TABLE sessions ADD COLUMN expires_at TEXT;
