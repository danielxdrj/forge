"""Travas read-only reais (FTP/Portainer/SQL): bloqueio em código, não só em prompt."""
from __future__ import annotations

import pytest

from forge_core.connections.readonly import (
    ReadOnlyFTP,
    ReadOnlyPortainerClient,
    ReadOnlySqlGuard,
    ReadOnlyViolation,
    assert_readonly_query,
    portainer_path_allowed,
    strip_sql_comments_and_strings,
)

# --- FTP ---------------------------------------------------------------------


def test_ftp_allows_read_commands():
    ftp = ReadOnlyFTP()
    ftp._check_command("LIST")
    ftp._check_command("RETR arquivo.txt")
    ftp._check_command("CWD /pasta")
    ftp._check_command("OPTS UTF8 ON")


@pytest.mark.parametrize("cmd", [
    "STOR arquivo.txt", "STOU", "APPE arquivo.txt", "DELE arquivo.txt", "RMD pasta",
    "MKD pasta", "RNFR a.txt", "RNTO b.txt", "SITE CHMOD 777 x", "CHMOD 777 x",
    "ABOR", "ALLO 10", "OPTS MLST type;",
])
def test_ftp_denies_write_commands(cmd):
    ftp = ReadOnlyFTP()
    with pytest.raises(ReadOnlyViolation):
        ftp._check_command(cmd)


def test_ftp_high_level_write_methods_denied_without_network():
    ftp = ReadOnlyFTP()
    with pytest.raises(ReadOnlyViolation):
        ftp.storbinary("STOR x", None)
    with pytest.raises(ReadOnlyViolation):
        ftp.delete("x")
    with pytest.raises(ReadOnlyViolation):
        ftp.rename("a", "b")
    with pytest.raises(ReadOnlyViolation):
        ftp.mkd("pasta")
    with pytest.raises(ReadOnlyViolation):
        ftp.rmd("pasta")


def test_ftp_putcmd_sendcmd_voidcmd_block_before_socket():
    ftp = ReadOnlyFTP()
    for method in (ftp.putcmd, ftp.sendcmd, ftp.voidcmd):
        with pytest.raises(ReadOnlyViolation):
            method("DELE segredo.txt")


# --- Portainer -----------------------------------------------------------------


@pytest.mark.parametrize("path", [
    "/api/status", "/api/endpoints", "/api/endpoints/1",
    "/api/endpoints/1/docker/containers/json",
    "/api/endpoints/1/docker/containers/abc123/json",
    "/api/endpoints/1/docker/containers/abc123/logs",
    "/api/endpoints/1/docker/containers/abc123/stats",
])
def test_portainer_allows_read_paths(path):
    assert portainer_path_allowed(path) is True


@pytest.mark.parametrize("path", [
    "/api/endpoints/1/docker/containers/abc/exec",
    "/api/endpoints/1/docker/containers/abc/restart",
    "/api/endpoints/1/docker/containers/abc/stop",
    "/api/endpoints/1/docker/containers/abc/kill",
    "/api/endpoints/1/docker/containers/abc/start",
    "/api/endpoints/1/docker/containers/create",
    "/api/endpoints/1/docker/containers/abc/remove",
    "/api/endpoints/1/docker/images/create",
    "/api/users",
    "/api/settings",
])
def test_portainer_denies_write_or_unlisted_paths(path):
    assert portainer_path_allowed(path) is False


def test_portainer_client_denies_non_get_method():
    client = ReadOnlyPortainerClient("http://host:9000", "token")
    with pytest.raises(ReadOnlyViolation):
        client.request("POST", "/api/status")
    with pytest.raises(ReadOnlyViolation):
        client.request("GET", "/api/endpoints/1/docker/containers/abc/restart")


def test_portainer_client_allows_get_status(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        return Resp()

    client = ReadOnlyPortainerClient("http://host:9000", "tok", urlopen_fn=fake_urlopen)
    with client.get("/api/status"):
        pass
    assert seen["url"] == "http://host:9000/api/status"
    assert seen["method"] == "GET"


# --- SQL -----------------------------------------------------------------------


@pytest.mark.parametrize("sql", [
    "SELECT * FROM users",
    "  select id from t where x = 1",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "EXPLAIN SELECT * FROM users",
    "SHOW TABLES",
    "SELECT 1;",
])
def test_sql_guard_allows_read_queries(sql):
    assert_readonly_query(sql)  # não levanta


@pytest.mark.parametrize("sql", [
    "INSERT INTO users (id) VALUES (1)",
    "UPDATE users SET x = 1",
    "DELETE FROM users",
    "MERGE INTO users USING x ON (1=1) WHEN MATCHED THEN UPDATE SET y=1",
    "DROP TABLE users",
    "ALTER TABLE users ADD COLUMN x int",
    "CREATE TABLE x (id int)",
    "TRUNCATE users",
    "GRANT ALL ON users TO bob",
    "REVOKE ALL ON users FROM bob",
    "COPY users TO '/tmp/x.csv'",
    "CALL some_proc()",
    "DO $$ BEGIN PERFORM 1; END $$",
    "VACUUM users",
    "LOCK TABLE users",
    "SET ROLE admin",
    "WITH x AS (DELETE FROM users RETURNING *) SELECT * FROM x",
])
def test_sql_guard_denies_write_queries(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_readonly_query(sql)


def test_sql_guard_denies_multiple_statements():
    with pytest.raises(ReadOnlyViolation):
        assert_readonly_query("SELECT 1; DROP TABLE users")


def test_sql_guard_denies_empty_query():
    with pytest.raises(ReadOnlyViolation):
        assert_readonly_query("")


def test_sql_guard_handles_comments_and_strings_hiding_dml():
    # DML escondido em comentário de linha/bloco não deve enganar o filtro:
    # a consulta inteira é tratada como um só comando e a palavra "DROP" como literal é ignorada,
    # mas colada fora de string/comentário ainda é recusada.
    assert_readonly_query("SELECT 'DROP TABLE users' AS warning_text")  # string: permitido
    with pytest.raises(ReadOnlyViolation):
        assert_readonly_query("SELECT 1; -- comentario\nDROP TABLE users")


def test_strip_sql_comments_and_strings_removes_dash_dash_and_block_and_dollar_quote():
    stripped = strip_sql_comments_and_strings(
        "SELECT 1 -- comentario\n/* bloco DROP */ , $$ texto DELETE $$"
    )
    assert "comentario" not in stripped
    assert "bloco" not in stripped
    assert "texto" not in stripped


class _FakeCursor:
    def __init__(self, store):
        self._store = store

    def execute(self, sql, params=None):
        self._store.append(sql)

    def close(self):
        pass


class _FakeConnection:
    def __init__(self):
        self.executed: list[str] = []

    def cursor(self):
        return _FakeCursor(self.executed)


def test_readonly_sql_guard_opens_readonly_session_once_then_validates():
    conn = _FakeConnection()
    guard = ReadOnlySqlGuard(conn, "postgres")
    guard.execute("SELECT 1")
    guard.execute("SELECT 2")
    assert conn.executed[0] == "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
    assert conn.executed[1] == "START TRANSACTION READ ONLY"
    assert conn.executed[2:] == ["SELECT 1", "SELECT 2"]


def test_readonly_sql_guard_mysql_dialect():
    conn = _FakeConnection()
    guard = ReadOnlySqlGuard(conn, "mysql")
    guard.execute("SELECT 1")
    assert conn.executed[0] == "SET SESSION TRANSACTION READ ONLY"


def test_readonly_sql_guard_rejects_write_before_touching_connection():
    conn = _FakeConnection()
    guard = ReadOnlySqlGuard(conn, "postgres")
    with pytest.raises(ReadOnlyViolation):
        guard.execute("DELETE FROM users")
    assert conn.executed == []


def test_readonly_sql_guard_unsupported_dialect():
    conn = _FakeConnection()
    guard = ReadOnlySqlGuard(conn, "mssql")
    with pytest.raises(ReadOnlyViolation):
        guard.execute("SELECT 1")
