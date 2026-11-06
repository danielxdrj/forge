"""Repositório SQL único para SQLite (stdlib) e PostgreSQL (psycopg, import tardio)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from ..errors import ConfigError
from ..logging import redact
from .migrate import migrate
from .repository import AuditEntry, Task, TaskEvent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqlRepository:
    """Toda escrita de tarefa grava o evento de histórico e a auditoria na mesma transação.

    Conteúdo livre (título, alvo, resultado) passa por redact() antes de ser gravado.
    """

    def __init__(self, conn, dialect: str):
        self._conn = conn
        self._ph = "?" if dialect == "sqlite" else "%s"
        self.dialect = dialect
        migrate(conn, dialect, self._ph)

    def _q(self, sql: str) -> str:
        return sql.replace("?", self._ph)

    def _run(self, writes: list[tuple[str, tuple]]) -> None:
        cur = self._conn.cursor()
        try:
            for sql, params in writes:
                cur.execute(self._q(sql), params)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _fetch(self, sql: str, params: tuple = ()) -> list[tuple]:
        cur = self._conn.cursor()
        cur.execute(self._q(sql), params)
        rows = cur.fetchall()
        self._conn.commit()
        return rows

    @staticmethod
    def _audit_write(actor: str, action: str, target: str, result: str) -> tuple[str, tuple]:
        return (
            "INSERT INTO audit_log (at, actor, action, target, result) VALUES (?, ?, ?, ?, ?)",
            (_now(), redact(actor), redact(action), redact(target), redact(result)),
        )

    def create_task(self, title: str, actor: str) -> Task:
        task_id, now, title = str(uuid.uuid4()), _now(), redact(title)
        self._run(
            [
                ("INSERT INTO tasks (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                 (task_id, title, "created", now, now)),
                ("INSERT INTO task_history (task_id, status, actor, at) VALUES (?, ?, ?, ?)",
                 (task_id, "created", redact(actor), now)),
                self._audit_write(actor, "task.create", f"task:{task_id}", "ok"),
            ]
        )
        return Task(task_id, title, "created", now, now)

    def set_task_status(self, task_id: str, status: str, actor: str) -> Task:
        if self.get_task(task_id) is None:
            self.record_audit(actor, "task.status", f"task:{task_id}", "error: tarefa inexistente")
            raise KeyError(task_id)
        now = _now()
        self._run(
            [
                ("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now, task_id)),
                ("INSERT INTO task_history (task_id, status, actor, at) VALUES (?, ?, ?, ?)",
                 (task_id, status, redact(actor), now)),
                self._audit_write(actor, "task.status", f"task:{task_id}", f"ok: {status}"),
            ]
        )
        return self.get_task(task_id)  # type: ignore[return-value]

    def get_task(self, task_id: str) -> Task | None:
        rows = self._fetch("SELECT id, title, status, created_at, updated_at FROM tasks WHERE id = ?", (task_id,))
        return Task(*rows[0]) if rows else None

    def list_tasks(self) -> list[Task]:
        rows = self._fetch("SELECT id, title, status, created_at, updated_at FROM tasks ORDER BY created_at, id")
        return [Task(*r) for r in rows]

    def task_history(self, task_id: str) -> list[TaskEvent]:
        rows = self._fetch("SELECT task_id, status, actor, at FROM task_history WHERE task_id = ? ORDER BY id", (task_id,))
        return [TaskEvent(*r) for r in rows]

    def record_audit(self, actor: str, action: str, target: str, result: str) -> None:
        self._run([self._audit_write(actor, action, target, result)])

    def list_audit(self) -> list[AuditEntry]:
        rows = self._fetch("SELECT id, at, actor, action, target, result FROM audit_log ORDER BY id")
        return [AuditEntry(*r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def open_repository(url: str) -> SqlRepository:
    """`sqlite:///caminho.db`, `sqlite:///:memory:` ou `postgresql://...` (URL nunca é logada)."""
    if url.startswith("sqlite:///"):
        return SqlRepository(sqlite3.connect(url[len("sqlite:///"):]), "sqlite")
    if url.startswith(("postgresql://", "postgres://")):
        try:
            import psycopg
        except ImportError as exc:
            raise ConfigError("PostgreSQL exige o pacote psycopg: pip install -e \".[postgres]\"") from exc
        return SqlRepository(psycopg.connect(url), "postgres")
    raise ConfigError("FORGE_DATABASE_URL deve começar com sqlite:/// ou postgresql://")
