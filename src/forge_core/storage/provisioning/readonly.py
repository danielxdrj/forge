"""Grants do papel forge_readonly: SELECT em tabelas, sem token_hash de sessão e sem escrita."""
from __future__ import annotations

import re

from .reprovision import ReprovisionError

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SESSION_COLS = ("id", "identity_id", "login", "created_at", "expires_at")


def apply_readonly_grants(conn, role: str) -> list[str]:
    """SELECT em todas as tabelas públicas, exceto sessions.token_hash (privilégio por coluna).

    Sem INSERT/UPDATE/DELETE/TRUNCATE, sem DDL, sem ownership. Idempotente. O papel já deve existir.
    """
    if not _ROLE.match(role):
        raise ReprovisionError("role_name_invalid")
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone() is None:
            raise ReprovisionError("role_missing")
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
        cur.execute(f"REVOKE SELECT ON TABLE sessions FROM {role}")
        cols = ", ".join(_SESSION_COLS)
        cur.execute(f"GRANT SELECT ({cols}) ON sessions TO {role}")
        conn.commit()
        return ["readonly_select_except_token_hash"]
    except ReprovisionError:
        conn.rollback()
        raise
    finally:
        cur.close()
