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
