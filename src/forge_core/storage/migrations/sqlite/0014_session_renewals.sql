-- Renovação deslizante de sessão: append-only, sem UPDATE em sessions.
CREATE TABLE session_renewals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    expires_at TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX session_renewals_session ON session_renewals (session_id);
CREATE TRIGGER session_renewals_no_update BEFORE UPDATE ON session_renewals BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER session_renewals_no_delete BEFORE DELETE ON session_renewals BEGIN SELECT RAISE(ABORT, 'append-only'); END;
