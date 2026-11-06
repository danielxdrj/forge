ALTER TABLE projects ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE projects ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE projects ADD COLUMN updated_at TEXT;
UPDATE projects SET updated_at = created_at;
CREATE TABLE repositories (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects (id),
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'github',
    owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    default_branch TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    settings TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX repositories_identity ON repositories (provider, lower(owner), lower(repo_name));
CREATE INDEX repositories_project ON repositories (project_id);
