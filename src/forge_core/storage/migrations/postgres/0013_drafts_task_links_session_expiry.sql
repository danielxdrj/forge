-- Rascunhos e vínculos de tarefa (PR A / ADR-017). Sessão web ganha expires_at; CLI legado permanece NULL.
CREATE TABLE drafts (
    id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES tasks (id),
    repo text NOT NULL,
    body_md text NOT NULL,
    tipo text NOT NULL,
    prioridade text NOT NULL,
    size text NOT NULL,
    preview_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('rascunho', 'confirmado', 'publicado', 'cancelado')),
    created_by text NOT NULL REFERENCES identities (id),
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE INDEX drafts_task ON drafts (task_id);
CREATE TABLE task_links (
    id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES tasks (id),
    kind text NOT NULL CHECK (kind IN ('issue', 'pr', 'branch')),
    repo text NOT NULL,
    number bigint,
    url text NOT NULL,
    board_item_id text,
    created_at text NOT NULL,
    UNIQUE (task_id, kind, url)
);
CREATE INDEX task_links_task ON task_links (task_id);
ALTER TABLE sessions ADD COLUMN expires_at text;
