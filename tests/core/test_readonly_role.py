"""Papel forge_readonly: SELECT em tasks, sem token_hash, sem INSERT (Postgres)."""
import uuid

import pytest

from auth_helpers import actor
from forge_core.storage.provisioning.readonly import apply_readonly_grants
from forge_core.tasks import TaskService

pytestmark = pytest.mark.usefixtures("pg_env")


def test_readonly_selects_tasks_but_not_token_hash_or_insert(pg_env):
    import os

    import psycopg
    from psycopg.conninfo import make_conninfo

    writer, owner_repo, _ = pg_env
    ana = actor(writer, "ana")
    TaskService(writer).create_task("visível ao leitor", ana)
    role = "forge_ro_" + uuid.uuid4().hex[:8]
    pwd = "senha-ficticia-" + role
    owner = owner_repo._conn
    owner.execute(
        f"CREATE ROLE {role} LOGIN PASSWORD '{pwd}' NOSUPERUSER NOCREATEDB NOCREATEROLE"
    )
    owner.execute(f"GRANT CONNECT ON DATABASE {owner.info.dbname} TO {role}")
    owner.commit()
    apply_readonly_grants(owner, role)

    conn = psycopg.connect(
        make_conninfo(os.environ["FORGE_DATABASE_URL"], dbname=owner.info.dbname, user=role, password=pwd)
    )
    try:
        rows = conn.execute("SELECT title FROM tasks").fetchall()
        assert any(r[0] == "visível ao leitor" for r in rows)
        conn.execute("SELECT id, login FROM sessions").fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT token_hash FROM sessions")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO tasks (id, title, status, created_at, updated_at) VALUES ('x', 'y', 'pending', 't', 't')")
        conn.rollback()
    finally:
        conn.close()
        owner.execute(f"DROP OWNED BY {role}")
        owner.execute(f"DROP ROLE {role}")
        owner.commit()
