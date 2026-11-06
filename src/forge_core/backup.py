"""Backup e restauração do adaptador SQLite. Para PostgreSQL, veja src/forge_core/README.md (pg_dump/pg_restore)."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _copy(src: Path, dest: Path) -> None:
    if Path(src).resolve() == Path(dest).resolve():
        raise ValueError("origem e destino devem ser diferentes")
    s, d = sqlite3.connect(src), sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        s.close()
        d.close()


def backup_sqlite(db_path: Path, backup_path: Path) -> None:
    _copy(db_path, backup_path)


def restore_sqlite(backup_path: Path, db_path: Path) -> None:
    """Sobrescreve o banco de destino. Pare o Forge antes."""
    if not Path(backup_path).exists():
        raise FileNotFoundError(backup_path)
    _copy(backup_path, db_path)
