"""Interface de repositório. O Core depende só disto, nunca de um banco específico."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    status: str
    actor: str
    at: str


@dataclass(frozen=True)
class AuditEntry:
    id: int
    at: str
    actor: str
    action: str
    target: str
    result: str


class Repository(Protocol):
    def create_task(self, title: str, actor: str) -> Task: ...

    def set_task_status(self, task_id: str, status: str, actor: str) -> Task: ...

    def get_task(self, task_id: str) -> Task | None: ...

    def list_tasks(self) -> list[Task]: ...

    def task_history(self, task_id: str) -> list[TaskEvent]: ...

    def record_audit(self, actor: str, action: str, target: str, result: str) -> None: ...

    def list_audit(self) -> list[AuditEntry]: ...

    def close(self) -> None: ...
