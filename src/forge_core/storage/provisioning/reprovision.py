"""Reprovisionamento de grants do papel escritor em bancos JÁ EXISTENTES (ADR-013, runbook).

Reaproveita `postgres_roles.sql`, sem a linha CREATE ROLE (o papel é criado pelo administrador). Os GRANTs são
idempotentes. Antes, recusa cenários inesperados (dono de tabela ou schema, membership, atributos
privilegiados, default privileges com o papel). Depois, confirma que o escritor não tem DELETE/TRUNCATE nem
UPDATE nas tabelas append-only. NÃO revoga acesso alheio: se PUBLIC ou outro papel der privilégio indevido,
a operação falha sanitizada e o administrador decide.

Uso (como o dono/migrador, em ambiente autorizado; nunca em startup):
    FORGE_DATABASE_MIGRATION_URL=... python -m forge_core.storage.provisioning.reprovision --role <PAPEL>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from ...errors import ForgeError

APPEND_ONLY = ("audit_log", "task_history", "task_changes", "agent_runs", "approval_consumptions", "grant_consumptions", "dispatch_requests", "agent_executions")
WRITER_MAY_DELETE = frozenset({"connections", "connection_hosts", "investigation_notes"})
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
SCRIPT = Path(__file__).with_name("postgres_roles.sql")


class ReprovisionError(ForgeError):
    """Falha sanitizada: carrega só um código fixo. Nunca nomes de objetos do banco, SQL ou segredo."""


_PRECHECK = """
SELECT r.rolsuper, r.rolbypassrls, r.rolcreatedb, r.rolcreaterole,
       (SELECT count(*) FROM pg_auth_members m WHERE m.member = r.oid),
       (SELECT count(*) FROM pg_tables t WHERE t.schemaname = 'public' AND t.tableowner = r.rolname),
       (SELECT count(*) FROM pg_namespace n WHERE n.nspowner = r.oid),
       (SELECT count(*) FROM pg_default_acl d WHERE position(r.rolname IN d.defaclacl::text) > 0)
FROM pg_roles r WHERE r.rolname = %s
"""


def _check(cur, code: str, ok: bool) -> str:
    if not ok:
        raise ReprovisionError(code)
    return code


def _precheck(cur, role: str) -> list[str]:
    cur.execute(_PRECHECK, (role,))
    row = cur.fetchone()
    if row is None:
        raise ReprovisionError("role_missing")
    sup, bypass, createdb, createrole, memberships, owned_tables, owned_schemas, default_acl = row
    checks = [
        _check(cur, "role_privileges_unexpected", not (sup or bypass or createdb or createrole)),
        _check(cur, "role_membership_unexpected", memberships == 0),
        _check(cur, "role_ownership_unexpected", owned_tables == 0 and owned_schemas == 0),
        _check(cur, "default_privileges_unexpected", default_acl == 0),
    ]
    cur.execute("SELECT pg_get_userbyid(c.relowner) = current_user FROM pg_class c "
                "WHERE c.relname = 'audit_log' AND c.relkind = 'r'")
    owner_row = cur.fetchone()
    checks.append(_check(cur, "connection_not_owner", bool(owner_row and owner_row[0])))
    return checks


def _grants_script(role: str, database: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if not l.startswith("CREATE ROLE")]
    return "\n".join(lines).replace("<PAPEL_APP>", role).replace("<BANCO>", database)


def _postcheck(cur, role: str) -> list[str]:
    checks = []
    for table in APPEND_ONLY:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
        if not cur.fetchone()[0]:
            raise ReprovisionError("append_only_table_missing")
        for priv in ("DELETE", "TRUNCATE", "UPDATE"):
            cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{table}", priv))
            if cur.fetchone()[0]:
                raise ReprovisionError("writer_privilege_unexpected")
        for priv in ("SELECT", "INSERT"):
            cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{table}", priv))
            if not cur.fetchone()[0]:
                raise ReprovisionError("writer_grant_missing")
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for (table,) in cur.fetchall():
        cur.execute("SELECT has_table_privilege(%s, %s, 'TRUNCATE')", (role, f"public.{table}"))
        if cur.fetchone()[0]:
            raise ReprovisionError("writer_delete_unexpected")
        if table in WRITER_MAY_DELETE:
            continue
        cur.execute("SELECT has_table_privilege(%s, %s, 'DELETE')", (role, f"public.{table}"))
        if cur.fetchone()[0]:
            raise ReprovisionError("writer_delete_unexpected")
    checks += ["append_only_no_update_delete_truncate", "writer_no_delete_truncate"]
    return checks


def reprovision(conn, role: str) -> list[str]:
    """Executa pré-checagens, aplica os GRANTs idempotentes e confirma. Devolve os códigos de verificação."""
    if not _ROLE.match(role):
        raise ReprovisionError("role_name_invalid")
    cur = conn.cursor()
    try:
        checks = _precheck(cur, role)
        cur.execute("SELECT current_database()")
        database = cur.fetchone()[0]
        if not _ROLE.match(database):
            raise ReprovisionError("database_name_unsupported")
        cur.execute(_grants_script(role, database))
        checks += _postcheck(cur, role)
        conn.commit()
        return checks
    except ReprovisionError:
        conn.rollback()
        raise
    finally:
        cur.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reprovision")
    parser.add_argument("--role", required=True)
    args = parser.parse_args(argv)
    url = os.environ.get("FORGE_DATABASE_MIGRATION_URL")
    if not url:
        print(json.dumps({"status": "error", "error": "migration_url_missing"}))
        return 2
    import psycopg

    try:
        with psycopg.connect(url) as conn:
            checks = reprovision(conn, args.role)
    except ReprovisionError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    except psycopg.Error:
        print(json.dumps({"status": "error", "error": "database_error"}))
        return 1
    print(json.dumps({"status": "ok", "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
