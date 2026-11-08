CREATE TABLE identities (
    id TEXT PRIMARY KEY,
    github_id INTEGER NOT NULL UNIQUE,
    login TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE bootstrap_owner (
    singleton TEXT PRIMARY KEY CHECK (singleton = 'owner'),
    identity_id TEXT NOT NULL REFERENCES identities(id),
    at TEXT NOT NULL
);
CREATE TABLE role_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id TEXT NOT NULL REFERENCES identities(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'approver')),
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL
);
CREATE TABLE role_revocations (
    grant_id INTEGER PRIMARY KEY REFERENCES role_grants(id),
    revoked_by TEXT NOT NULL,
    revoked_at TEXT NOT NULL
);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL REFERENCES identities(id),
    token_hash TEXT NOT NULL UNIQUE,
    login TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE session_revocations (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
    revoked_at TEXT NOT NULL
);
CREATE TABLE approval_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    task_version INTEGER NOT NULL,
    identity_id TEXT NOT NULL REFERENCES identities(id),
    granted_at TEXT NOT NULL
);
CREATE TRIGGER identities_no_update BEFORE UPDATE ON identities BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER identities_no_delete BEFORE DELETE ON identities BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER bootstrap_owner_no_update BEFORE UPDATE ON bootstrap_owner BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER bootstrap_owner_no_delete BEFORE DELETE ON bootstrap_owner BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER role_grants_no_update BEFORE UPDATE ON role_grants BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER role_grants_no_delete BEFORE DELETE ON role_grants BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER role_revocations_no_update BEFORE UPDATE ON role_revocations BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER role_revocations_no_delete BEFORE DELETE ON role_revocations BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER sessions_no_update BEFORE UPDATE ON sessions BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER sessions_no_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER session_revocations_no_update BEFORE UPDATE ON session_revocations BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER session_revocations_no_delete BEFORE DELETE ON session_revocations BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER approval_grants_no_update BEFORE UPDATE ON approval_grants BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER approval_grants_no_delete BEFORE DELETE ON approval_grants BEGIN SELECT RAISE(ABORT, 'append-only'); END;
