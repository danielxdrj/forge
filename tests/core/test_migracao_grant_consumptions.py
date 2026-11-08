"""Upgrade de banco existente em 0009/0010: ledger legado com ids colidentes, SQLite e Postgres."""
import sqlite3

from forge_core.storage import SqlRepository, open_repository
from forge_core.storage.migrate import migrate


def _seed_ledger(conn, ph: str, *, also_grant_consumptions: bool) -> None:
    """Banco já migrado até 0009 (e opcionalmente 0010). Sem TaskService: só SQL, como um banco antigo."""
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO identities (id, github_id, login, created_at) VALUES ({ph},{ph},{ph},{ph})",
        ("gh:1000", 1000, "dona", "2026-01-01T00:00:00+00:00"))
    # Consumo de auditoria antiga com grant_id=1, tarefa e momento que NÃO batem com a concessão nova.
    cur.execute(
        f"INSERT INTO approval_consumptions (grant_id, task_id, agent, consumed_by, consumed_at) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph})",
        (1, "audit-legado", "old", "agente:x", "2020-01-01T00:00:00+00:00"))
    cur.execute(
        f"INSERT INTO approval_grants (task_id, agent, task_version, identity_id, granted_at) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph})",
        ("t-livre", "echo", 1, "gh:1000", "2026-06-01T00:00:00+00:00"))  # id 1, colide em número
    cur.execute(
        f"INSERT INTO approval_grants (task_id, agent, task_version, identity_id, granted_at) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph})",
        ("t-gasto", "echo", 1, "gh:1000", "2026-06-01T00:00:00+00:00"))  # id 2
    cur.execute(
        f"INSERT INTO approval_consumptions (grant_id, task_id, agent, consumed_by, consumed_at) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph})",
        (2, "t-gasto", "echo", "agente:orch", "2026-06-02T00:00:00+00:00"))
    if also_grant_consumptions:
        cur.execute(
            f"INSERT INTO grant_consumptions (grant_id, task_id, agent, consumed_by, consumed_at) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph})",
            (2, "t-gasto", "echo", "agente:orch", "2026-06-02T00:00:00+00:00"))
    conn.commit()


def _assert_upgraded(repo):
    legado = repo.fetch("SELECT grant_id, task_id FROM approval_consumptions ORDER BY grant_id")
    assert legado == [(1, "audit-legado"), (2, "t-gasto")]
    copied = repo.fetch("SELECT grant_id, task_id FROM grant_consumptions ORDER BY grant_id")
    assert copied == [(2, "t-gasto")]
    # a concessão colidente (id 1) continua disponível; a real (id 2) permanece gasta
    livre = repo.fetch(
        "SELECT COUNT(*) FROM approval_grants g WHERE g.id = 1 AND NOT EXISTS "
        "(SELECT 1 FROM grant_consumptions c WHERE c.grant_id = g.id)")[0][0]
    assert livre == 1
    versions = [r[0][:4] for r in repo.fetch("SELECT version FROM schema_migrations ORDER BY version")]
    assert "0011" in versions and "0012" in versions


def test_sqlite_upgrade_from_0009_with_colliding_legacy_ids(tmp_path):
    path = tmp_path / "antigo.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    assert migrate(conn, "sqlite", "?", up_to="0009")[-1].startswith("0009")
    _seed_ledger(conn, "?", also_grant_consumptions=False)
    conn.close()
    repo = open_repository(f"sqlite:///{path}")
    _assert_upgraded(repo)
    open_repository(f"sqlite:///{path}").close()  # reaplicar: no-op
    _assert_upgraded(repo)


def test_sqlite_upgrade_from_0010_preserves_existing_grant_consumptions(tmp_path):
    path = tmp_path / "v10.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    assert migrate(conn, "sqlite", "?", up_to="0010")[-1].startswith("0010")
    _seed_ledger(conn, "?", also_grant_consumptions=True)
    conn.close()
    repo = open_repository(f"sqlite:///{path}")
    _assert_upgraded(repo)


def test_postgres_upgrade_from_0009_with_colliding_legacy_ids(pg_blank):
    conn = pg_blank
    assert migrate(conn, "postgres", "%s", up_to="0009")[-1].startswith("0009")
    _seed_ledger(conn, "%s", also_grant_consumptions=False)
    repo = SqlRepository(conn, "postgres")  # aplica 0010+ no mesmo banco existente
    _assert_upgraded(repo)
    SqlRepository(conn, "postgres")  # reaplicar
    _assert_upgraded(repo)


def test_postgres_upgrade_from_0010_preserves_existing_grant_consumptions(pg_blank):
    conn = pg_blank
    assert migrate(conn, "postgres", "%s", up_to="0010")[-1].startswith("0010")
    _seed_ledger(conn, "%s", also_grant_consumptions=True)
    repo = SqlRepository(conn, "postgres")
    _assert_upgraded(repo)
