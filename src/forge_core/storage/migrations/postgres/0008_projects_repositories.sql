ALTER TABLE projects ADD COLUMN description text NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN active integer NOT NULL DEFAULT 1;
ALTER TABLE projects ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE projects ADD COLUMN updated_at text;
UPDATE projects SET updated_at = created_at;
CREATE TABLE repositories (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (id),
    name text NOT NULL,
    provider text NOT NULL DEFAULT 'github',
    owner text NOT NULL,
    repo_name text NOT NULL,
    default_branch text NOT NULL,
    active integer NOT NULL DEFAULT 1,
    settings text NOT NULL DEFAULT '{}',
    version integer NOT NULL DEFAULT 1,
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE UNIQUE INDEX repositories_identity ON repositories (provider, lower(owner), lower(repo_name));
CREATE INDEX repositories_project ON repositories (project_id);
