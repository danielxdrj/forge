-- Cadastro de conexões (cofre cifrado no próprio Forge). Segredo só em secret_ciphertext.
CREATE TABLE connections (
    id text PRIMARY KEY,
    name text NOT NULL,
    type text NOT NULL CHECK (type IN ('mysql', 'postgres', 'ftp', 'sftp', 'portainer')),
    username text NOT NULL,
    port integer NOT NULL CHECK (port >= 1 AND port <= 65535),
    database_name text,
    remote_path text,
    secret_ciphertext text,
    preferred_host_id text,
    created_at text NOT NULL,
    updated_at text NOT NULL
);
CREATE TABLE connection_hosts (
    id text PRIMARY KEY,
    connection_id text NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    label text NOT NULL,
    hostname text NOT NULL,
    sort_order integer NOT NULL,
    created_at text NOT NULL
);
CREATE INDEX connection_hosts_connection ON connection_hosts (connection_id, sort_order);
