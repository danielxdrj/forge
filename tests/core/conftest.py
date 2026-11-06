import os
import uuid
from pathlib import Path

import pytest

PG_URL = os.environ.get("FORGE_DATABASE_URL")


@pytest.fixture
def pg_env():
    """Banco e papel escritor efêmeros. FORGE_DATABASE_URL precisa poder CREATE DATABASE/ROLE (dono/migrador).

    Devolve (writer, owner_repo, new_writer); new_writer() abre outra conexão como escritor.
    """
    if not PG_URL:
        pytest.skip("FORGE_DATABASE_URL não definida")
    import psycopg
    from psycopg.conninfo import make_conninfo

    import forge_core.storage.sql as sql_mod
    from forge_core.storage import SqlRepository

    suffix = uuid.uuid4().hex[:8]
    db, role, pwd = f"forge_t_{suffix}", f"forge_app_{suffix}", "senha-ficticia-" + suffix
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f"CREATE DATABASE {db}")
    owner = psycopg.connect(make_conninfo(PG_URL, dbname=db))
    SqlRepository(owner, "postgres")
    prov = (Path(sql_mod.__file__).parent / "provisioning" / "postgres_roles.sql").read_text()
    prov = prov.replace("<PAPEL_APP>", role).replace("<SEGREDO_APP>", pwd).replace("<BANCO>", db)
    prov = "\n".join(l for l in prov.splitlines() if not l.startswith("--"))
    owner.execute(prov)
    owner.commit()
    opened = []

    def new_writer():
        repo = SqlRepository(
            psycopg.connect(make_conninfo(PG_URL, dbname=db, user=role, password=pwd)), "postgres", run_migrations=False
        )
        opened.append(repo)
        return repo

    writer = new_writer()
    owner_repo = SqlRepository(owner, "postgres", run_migrations=False)
    writer.record_audit("pessoa:ana", "seed", "t", "ok")
    yield writer, owner_repo, new_writer
    for repo in opened:
        repo.close()
    owner.close()
    admin.execute(f"DROP DATABASE {db} WITH (FORCE)")
    admin.execute(f"DROP ROLE {role}")
    admin.close()


@pytest.fixture
def pg_blank():
    """Conexão (dono) a um banco efêmero SEM migrações, para testar migração com dados existentes."""
    if not PG_URL:
        pytest.skip("FORGE_DATABASE_URL não definida")
    import psycopg
    from psycopg.conninfo import make_conninfo

    db = f"forge_b_{uuid.uuid4().hex[:8]}"
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f"CREATE DATABASE {db}")
    conn = psycopg.connect(make_conninfo(PG_URL, dbname=db))
    yield conn
    conn.close()
    admin.execute(f"DROP DATABASE {db} WITH (FORCE)")
    admin.close()


@pytest.fixture(params=["sqlite", "postgres"])
def make_repo(request, tmp_path):
    """Fábrica de repositórios (nova conexão a cada chamada) em SQLite e, se disponível, Postgres (escritor)."""
    if request.param == "sqlite":
        from forge_core.storage import open_repository

        return lambda: open_repository(f"sqlite:///{tmp_path / 'o.db'}")
    _, _, new_writer = request.getfixturevalue("pg_env")
    return new_writer


@pytest.fixture(autouse=True)
def _forge_env(monkeypatch):
    """Config mínima no ambiente: o Orchestrator/Runtime sem settings leem o ambiente (como o start())."""
    monkeypatch.setenv("FORGE_CONFIG_DIR", "cfg.example.invalid")
    monkeypatch.delenv("FORGE_AUTOMATION_ENABLED", raising=False)
    monkeypatch.delenv("FORGE_AGENTS_DISABLED", raising=False)
