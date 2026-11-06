"""Runner de migrações: arquivos SQL numerados + tabela schema_migrations."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(__file__).parent / "migrations"


def pending_migrations(dialect: str) -> list[Path]:
    return sorted((_DIR / dialect).glob("[0-9][0-9][0-9][0-9]_*.sql"))


def migrate(conn, dialect: str, ph: str, up_to: str | None = None) -> list[str]:
    """Aplica as migrações pendentes, cada uma numa transação. `up_to` ("0004") para nesse número (testes)."""
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    conn.commit()
    cur.execute("SELECT version FROM schema_migrations")
    done = {row[0] for row in cur.fetchall()}
    applied: list[str] = []
    for path in pending_migrations(dialect):
        version = path.stem
        if up_to is not None and version[:4] > up_to:
            break
        if version in done:
            continue
        try:
            for stmt in _statements(path.read_text(encoding="utf-8"), dialect):
                cur.execute(stmt)
            cur.execute(
                f"INSERT INTO schema_migrations (version, applied_at) VALUES ({ph}, {ph})",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append(version)
    return applied


def _statements(sql: str, dialect: str) -> list[str]:
    """SQLite executa um comando por vez; PostgreSQL aceita o arquivo inteiro (inclui funções $$)."""
    if dialect != "sqlite":
        return [sql]
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ""
    return out
