"""Reprovisionamento de grants em banco existente (ADR-013). Roda só com Postgres efêmero."""
import pytest

from forge_core.errors import ForgeError
from forge_core.storage.provisioning.reprovision import ReprovisionError, reprovision
from forge_core.tasks import TaskService

pytestmark = pytest.mark.usefixtures("pg_env")


def _role(writer):
    return writer._conn.info.user


def _owner(owner_repo):
    return owner_repo._conn


def _has(writer, table, priv):
    writer._conn.commit()  # sem transação aberta: enxerga os GRANTs já confirmados pelo dono
    cur = writer._conn.cursor()
    cur.execute("SELECT has_table_privilege(%s, %s)", (f"public.{table}", priv))
    val = cur.fetchone()[0]
    cur.close()
    return val


def _simulate_old_database(owner_repo, role):
    """Banco antigo: sem os grants que a FRG-5 e a FRG-24 acrescentaram."""
    conn = _owner(owner_repo)
    conn.execute(f"REVOKE UPDATE ON projects FROM {role}")
    conn.execute(f"REVOKE ALL ON repositories, approval_consumptions FROM {role}")
    conn.commit()


def test_old_database_is_repaired_and_reapplying_is_idempotent(pg_env):
    writer, owner_repo, _ = pg_env
    role = _role(writer)
    svc = TaskService(writer)
    before = svc.create_task("dados antes", "pessoa:ana")
    _simulate_old_database(owner_repo, role)
    assert not _has(writer, "projects", "UPDATE")

    checks1 = reprovision(_owner(owner_repo), role)
    assert "writer_no_delete_truncate" in checks1
    assert _has(writer, "projects", "UPDATE") and _has(writer, "repositories", "INSERT")
    assert not _has(writer, "approval_consumptions", "DELETE")

    checks2 = reprovision(_owner(owner_repo), role)
    assert checks2 == checks1
    assert svc.get_task(before.id).title == "dados antes"
    assert len(writer.fetch("SELECT id FROM tasks")) == 1
    assert len(writer.fetch("SELECT id FROM audit_log WHERE action = 'task.create'")) >= 1


@pytest.mark.parametrize("table", ["audit_log", "task_history", "task_changes", "agent_runs",
                                   "approval_consumptions"])
def test_writer_cannot_delete_truncate_or_update_append_only(pg_env, table):
    import psycopg

    writer, owner_repo, _ = pg_env
    reprovision(_owner(owner_repo), _role(writer))
    for sql in (f"DELETE FROM {table}", f"TRUNCATE {table}", f"UPDATE {table} SET task_id = task_id" if table in ("approval_consumptions",) else f"UPDATE {table} SET actor = actor"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            writer._conn.execute(sql)
        writer._conn.rollback()


def test_refuses_unexpected_membership_sanitized(pg_env):
    writer, owner_repo, _ = pg_env
    role = _role(writer)
    conn = _owner(owner_repo)
    conn.execute(f"GRANT pg_read_all_data TO {role}")
    conn.commit()
    try:
        with pytest.raises(ReprovisionError) as ei:
            reprovision(conn, role)
        assert ei.value.args[0] == "role_membership_unexpected"
    finally:
        conn.execute(f"REVOKE pg_read_all_data FROM {role}")
        conn.commit()


def test_refuses_writer_owning_a_table(pg_env):
    writer, owner_repo, _ = pg_env
    role = _role(writer)
    conn = _owner(owner_repo)
    conn.execute("CREATE TABLE public.reprov_dono (x int)")
    conn.execute(f"ALTER TABLE public.reprov_dono OWNER TO {role}")
    conn.commit()
    try:
        with pytest.raises(ReprovisionError) as ei:
            reprovision(conn, role)
        assert ei.value.args[0] == "role_ownership_unexpected"
    finally:
        conn.execute("DROP TABLE public.reprov_dono")
        conn.commit()


def test_refuses_public_delete_on_append_only_without_revoking_others(pg_env):
    writer, owner_repo, _ = pg_env
    role = _role(writer)
    conn = _owner(owner_repo)
    conn.execute("GRANT DELETE ON audit_log TO PUBLIC")
    conn.commit()
    try:
        with pytest.raises(ReprovisionError) as ei:
            reprovision(conn, role)
        assert ei.value.args[0] == "writer_privilege_unexpected"
        assert _has(writer, "audit_log", "DELETE")  # não revoga acesso alheio
    finally:
        conn.execute("REVOKE DELETE ON audit_log FROM PUBLIC")
        conn.commit()


def test_refusal_message_never_echoes_input(pg_env):
    writer, owner_repo, _ = pg_env
    with pytest.raises(ForgeError) as ei:
        reprovision(_owner(owner_repo), "papel-com-hifen")
    assert "papel" not in str(ei.value)
    assert ei.value.args[0] == "role_name_invalid"
    with pytest.raises(ReprovisionError) as ei:
        reprovision(_owner(owner_repo), "papel_inexistente_xyz")
    assert ei.value.args[0] == "role_missing"
