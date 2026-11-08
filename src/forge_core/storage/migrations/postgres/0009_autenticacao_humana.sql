CREATE TABLE identities (
    id text PRIMARY KEY,
    github_id bigint NOT NULL UNIQUE,
    login text NOT NULL,
    created_at text NOT NULL
);
CREATE TABLE bootstrap_owner (
    singleton text PRIMARY KEY CHECK (singleton = 'owner'),
    identity_id text NOT NULL REFERENCES identities(id),
    at text NOT NULL
);
CREATE TABLE role_grants (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identity_id text NOT NULL REFERENCES identities(id),
    role text NOT NULL CHECK (role IN ('owner', 'editor', 'approver')),
    granted_by text NOT NULL,
    granted_at text NOT NULL
);
CREATE TABLE role_revocations (
    grant_id bigint PRIMARY KEY REFERENCES role_grants(id),
    revoked_by text NOT NULL,
    revoked_at text NOT NULL
);
CREATE TABLE sessions (
    id text PRIMARY KEY,
    identity_id text NOT NULL REFERENCES identities(id),
    token_hash text NOT NULL UNIQUE,
    login text NOT NULL,
    created_at text NOT NULL
);
CREATE TABLE session_revocations (
    session_id text PRIMARY KEY REFERENCES sessions(id),
    revoked_at text NOT NULL
);
CREATE TABLE approval_grants (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id text NOT NULL,
    agent text NOT NULL,
    task_version bigint NOT NULL,
    identity_id text NOT NULL REFERENCES identities(id),
    granted_at text NOT NULL
);
CREATE TRIGGER identities_no_change BEFORE UPDATE OR DELETE ON identities
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER bootstrap_owner_no_change BEFORE UPDATE OR DELETE ON bootstrap_owner
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER role_grants_no_change BEFORE UPDATE OR DELETE ON role_grants
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER role_revocations_no_change BEFORE UPDATE OR DELETE ON role_revocations
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER sessions_no_change BEFORE UPDATE OR DELETE ON sessions
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER session_revocations_no_change BEFORE UPDATE OR DELETE ON session_revocations
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER approval_grants_no_change BEFORE UPDATE OR DELETE ON approval_grants
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER identities_no_truncate BEFORE TRUNCATE ON identities FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER role_grants_no_truncate BEFORE TRUNCATE ON role_grants FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER approval_grants_no_truncate BEFORE TRUNCATE ON approval_grants FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
