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

    def __init__(self, conn, dialect: str, run_migrations: bool = True):
        self._conn = conn
        self._ph = "?" if dialect == "sqlite" else "%s"
        self.dialect = dialect
        if dialect == "sqlite":
            # Sem isto o SQLite ignora FOREIGN KEY: apagar tarefa com histórico deixaria órfãos.
            conn.execute("PRAGMA foreign_keys = ON")
        if run_migrations:
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


def _connect(url: str):
    if url.startswith("sqlite:///"):
        return sqlite3.connect(url[len("sqlite:///"):]), "sqlite"
    if url.startswith(("postgresql://", "postgres://")):
        try:
            import psycopg
        except ImportError as exc:
            raise ConfigError("PostgreSQL exige o pacote psycopg: pip install -e \".[postgres]\"") from exc
        return psycopg.connect(url), "postgres"
    raise ConfigError("URL do banco deve começar com sqlite:/// ou postgresql://")


def migrate_database(migration_url: str) -> None:
    """Aplica as migrações com o papel dono/migrador. A aplicação não usa esse papel."""
    conn, dialect = _connect(migration_url)
    try:
        SqlRepository(conn, dialect, run_migrations=True)
    finally:
        conn.close()


def open_repository(url: str, migration_url: str | None = None) -> SqlRepository:
    """Abre o repositório com o papel da aplicação (URLs nunca são logadas).

    Com `migration_url`, migra antes com o papel dono e a aplicação conecta só como escritora.
    Sem ela, migra com a própria `url` (SQLite e desenvolvimento).
    """
    if migration_url:
        migrate_database(migration_url)
    conn, dialect = _connect(url)
    return SqlRepository(conn, dialect, run_migrations=migration_url is None)
