import os
import sqlite3

import pytest

from forge_core.backup import backup_sqlite, restore_sqlite
from forge_core.config import load_settings
from forge_core.errors import ConfigError
from forge_core.storage import open_repository
from forge_core.storage.migrate import pending_migrations


def sqlite_url(tmp_path, name="forge.db"):
    return f"sqlite:///{tmp_path / name}"


def test_migrations_apply_once(tmp_path):
    url = sqlite_url(tmp_path)
    open_repository(url).close()
    repo = open_repository(url)
    rows = repo._fetch("SELECT version FROM schema_migrations")
    assert [r[0] for r in rows] == [p.stem for p in pending_migrations("sqlite")]


def test_task_history_and_audit(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    t = repo.create_task("investigar", "agente:triagem")
    repo.set_task_status(t.id, "running", "pessoa:ana")
    assert [e.status for e in repo.task_history(t.id)] == ["created", "running"]
    audit = repo.list_audit()
    assert [(a.actor, a.action, a.target, a.result) for a in audit] == [
        ("agente:triagem", "task.create", f"task:{t.id}", "ok"),
        ("pessoa:ana", "task.status", f"task:{t.id}", "ok: running"),
    ]


def test_unknown_task_is_audited_and_raises(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    with pytest.raises(KeyError):
        repo.set_task_status("nao-existe", "x", "pessoa:ana")
    assert repo.list_audit()[-1].result.startswith("error")


def test_data_survives_restart(tmp_path):
    url = sqlite_url(tmp_path)
    r1 = open_repository(url)
    t = r1.create_task("persistir", "pessoa:ana")
    r1.close()
    r2 = open_repository(url)
    assert r2.get_task(t.id).title == "persistir"
    assert len(r2.list_audit()) == 1


def test_audit_is_append_only(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    repo.record_audit("pessoa:ana", "x", "y", "ok")
    with pytest.raises(sqlite3.DatabaseError):
        repo._conn.execute("UPDATE audit_log SET result = 'z'")
    with pytest.raises(sqlite3.DatabaseError):
        repo._conn.execute("DELETE FROM audit_log")


def test_secrets_are_masked_in_storage(tmp_path):
    repo = open_repository(sqlite_url(tmp_path))
    t = repo.create_task("usar token=abc123 e Bearer seg redo", "pessoa:ana")
    repo.record_audit("pessoa:ana", "call", "api", "Authorization: Bearer seg redo")
    dump = repr(repo.get_task(t.id)) + repr(repo.list_audit())
    for s in ("abc123", "seg", "redo"):
        assert s not in dump


def test_backup_and_restore_roundtrip(tmp_path):
    url = sqlite_url(tmp_path)
    repo = open_repository(url)
    t = repo.create_task("importante", "pessoa:ana")
    repo.close()
    backup_sqlite(tmp_path / "forge.db", tmp_path / "bkp.db")
    (tmp_path / "forge.db").unlink()
    restore_sqlite(tmp_path / "bkp.db", tmp_path / "forge.db")
    restored = open_repository(url)
    assert restored.get_task(t.id).title == "importante"
    assert len(restored.list_audit()) == 1


def test_database_url_validation_and_not_in_repr():
    with pytest.raises(ConfigError, match="FORGE_DATABASE_URL"):
        load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_DATABASE_URL": "mysql://x"})
    s = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_DATABASE_URL": "postgresql://u:senha-ficticia@example.invalid/db"})
    assert "senha-ficticia" not in repr(s)


@pytest.mark.skipif(not os.environ.get("FORGE_DATABASE_URL"), reason="FORGE_DATABASE_URL não definida")
def test_postgres_adapter():
    repo = open_repository(os.environ["FORGE_DATABASE_URL"])
    t = repo.create_task("pg", "pessoa:ana")
    repo.set_task_status(t.id, "done", "pessoa:ana")
    assert [e.status for e in repo.task_history(t.id)] == ["created", "done"]
    with pytest.raises(Exception):
        repo._run([("DELETE FROM audit_log", ())])
