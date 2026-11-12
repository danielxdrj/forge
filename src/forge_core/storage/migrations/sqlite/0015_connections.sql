-- Cadastro de conexões (cofre cifrado no próprio Forge). Segredo só em secret_ciphertext.
CREATE TABLE connections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('mysql', 'postgres', 'ftp', 'sftp', 'portainer')),
    username TEXT NOT NULL,
    port INTEGER NOT NULL CHECK (port >= 1 AND port <= 65535),
    database_name TEXT,
    remote_path TEXT,
    secret_ciphertext TEXT,
    preferred_host_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE connection_hosts (
    id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    hostname TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX connection_hosts_connection ON connection_hosts (connection_id, sort_order);
