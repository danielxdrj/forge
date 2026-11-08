import os
import sqlite3

import pytest

from auth_helpers import actor
from forge_core.backup import backup_sqlite, restore_sqlite
from forge_core.config import load_settings
from forge_core.errors import ConfigError
from forge_core.storage import open_repository
from forge_core.storage.migrate import pending_migrations
from forge_core.tasks import TaskService, TaskStatus as S


def sqlite_url(tmp_path, name="forge.db"):
    return f"sqlite:///{tmp_path / name}"


def _task(repo, title):
    return TaskService(repo).create_task(title, actor(repo, "ana"))


def _start(repo, task_id):
    return TaskService(repo).change_status(task_id, S.IN_PROGRESS, actor(repo, "ana"))


def test_migrations_apply_once(tmp_path):
    url = sqlite_url(tmp_path)
    open_repository(url).close()
    repo = open_repository(url)
    rows = repo._fetch("SELECT version FROM schema_migrations")
    assert [r[0] for r in rows] == [p.stem for p in pending_migrations("sqlite")]


def test_task_history_and_audit(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    t = _task(repo, "investigar")
    _start(repo, t.id)
    assert [e.status for e in repo.task_history(t.id)] == ["pending", "in_progress"]
    task_audit = [a for a in repo.list_audit() if a.target == f"task:{t.id}"]
    assert [(a.actor, a.action, a.result) for a in task_audit] == [
        ("gh:1001", "task.create", "ok"),
        ("gh:1001", "task.status", "ok: pending -> in_progress"),
    ]


def test_legacy_status_write_is_refused_and_writes_nothing(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    with pytest.raises(ConfigError):
        repo.set_task_status("nao-existe", "x", "sistema:teste")
    assert repo.list_audit() == []


def test_data_survives_restart(tmp_path):
    url = sqlite_url(tmp_path)
    r1 = open_repository(url)
    t = _task(r1, "persistir")
    r1.close()
    r2 = open_repository(url)
    assert r2.get_task(t.id).title == "persistir"
    assert [a.action for a in r2.list_audit() if a.action == "task.create"] == ["task.create"]


def test_audit_is_append_only(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    repo.record_audit("sistema:teste", "x", "y", "ok")
    with pytest.raises(sqlite3.DatabaseError):
        repo._conn.execute("UPDATE audit_log SET result = 'z'")
    with pytest.raises(sqlite3.DatabaseError):
        repo._conn.execute("DELETE FROM audit_log")


def test_secrets_are_masked_in_storage(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    t = _task(repo, "usar token=abc123 e Bearer seg redo")
    repo.record_audit("sistema:teste", "call", "api", "Authorization: Bearer seg redo")
    dump = repr(repo.get_task(t.id)) + repr(repo.list_audit())
    for s in ("abc123", "seg", "redo"):
        assert s not in dump


def test_backup_and_restore_roundtrip(tmp_path):
    url = sqlite_url(tmp_path)
    repo = open_repository(url)
    t = _task(repo, "importante")
    repo.close()
    backup_sqlite(tmp_path / "forge.db", tmp_path / "bkp.db")
    (tmp_path / "forge.db").unlink()
    restore_sqlite(tmp_path / "bkp.db", tmp_path / "forge.db")
    restored = open_repository(url)
    assert restored.get_task(t.id).title == "importante"
    assert len([a for a in restored.list_audit() if a.action == "task.create"]) == 1


def test_database_url_validation_and_not_in_repr():
    with pytest.raises(ConfigError, match="FORGE_DATABASE_URL"):
        load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_DATABASE_URL": "mysql://x"})
    s = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_DATABASE_URL": "postgresql://u:senha-ficticia@example.invalid/db"})
    assert "senha-ficticia" not in repr(s)


def test_sqlite_foreign_keys_on_blocks_orphan_history(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    assert repo._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    t = _task(repo, "com histórico")
    with pytest.raises(sqlite3.IntegrityError):
        repo._conn.execute("DELETE FROM tasks WHERE id = ?", (t.id,))
    assert repo.get_task(t.id) is not None and len(repo.task_history(t.id)) == 1


def test_sqlite_foreign_keys_on_for_every_connection(tmp_path):
    open_repository(sqlite_url(tmp_path)).close()
    second = open_repository(sqlite_url(tmp_path))
    assert second._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migration_url_migrates_and_app_connects_separately(tmp_path):
    url = sqlite_url(tmp_path)
    repo = open_repository(url, migration_url=url)
    assert repo.list_tasks() == []


PG_URL = os.environ.get("FORGE_DATABASE_URL")
pg = pytest.mark.skipif(not PG_URL, reason="FORGE_DATABASE_URL não definida")


@pg
def test_postgres_task_flow_with_writer_role(pg_env):
    writer, _, _ = pg_env
    t = _task(writer, "pg")
    _start(writer, t.id)
    assert [e.status for e in writer.task_history(t.id)] == ["pending", "in_progress"]


@pg
@pytest.mark.parametrize("sql", ["UPDATE audit_log SET result = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"])
def test_postgres_writer_cannot_change_audit(pg_env, sql):
    import psycopg

    writer, _, _ = pg_env
    _task(writer, "auditoria")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])
    assert len([a for a in writer.list_audit() if a.action == "task.create"]) == 1


@pg
def test_postgres_writer_is_not_owner_and_cannot_drop_trigger(pg_env):
    import psycopg

    writer, _, _ = pg_env
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([("DROP TRIGGER audit_log_no_truncate ON audit_log", ())])


@pg
@pytest.mark.parametrize("sql", ["TRUNCATE audit_log", "UPDATE audit_log SET result = 'x'", "DELETE FROM audit_log"])
def test_postgres_owner_blocked_by_trigger(pg_env, sql):
    import psycopg

    writer, owner, _ = pg_env
    _task(writer, "auditoria")
    with pytest.raises(psycopg.errors.RaiseException):
        owner._run([(sql, ())])
    assert len([a for a in writer.list_audit() if a.action == "task.create"]) == 1
