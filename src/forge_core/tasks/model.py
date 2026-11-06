"""Modelo de tarefa (ADR-010). Dados puros, sem banco."""
from __future__ import annotations

from dataclasses import dataclass


class TaskStatus:
    PLANNED = "planned"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_VALIDATION = "in_validation"
    DONE = "done"
    CANCELLED = "cancelled"
    ALL = (PLANNED, PENDING, IN_PROGRESS, BLOCKED, IN_VALIDATION, DONE, CANCELLED)
    TERMINAL = (DONE, CANCELLED)
    INITIAL = (PLANNED, PENDING)


class Priority:
    LOW, NORMAL, HIGH, URGENT = "low", "normal", "high", "urgent"
    ALL = (LOW, NORMAL, HIGH, URGENT)


class AssigneeKind:
    PERSON = "person"
    AGENT = "agent"
    ALL = (PERSON, AGENT)


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    objective: str
    context: str
    scope: str
    acceptance_criteria: str
    priority: str
    status: str
    assignee_kind: str | None
    assignee_id: str | None
    start_date: str | None
    due_date: str | None
    completed_at: str | None
    stage_id: str | None
    parent_task_id: str | None
    required: bool
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Dependency:
    task_id: str
    depends_on_id: str
    required: bool


@dataclass(frozen=True)
class Project:
    id: str
    title: str
    created_at: str


@dataclass(frozen=True)
class Stage:
    id: str
    project_id: str
    title: str
    created_at: str


@dataclass(frozen=True)
class TaskChange:
    task_id: str
    field: str
    old_value: str | None
    new_value: str | None
    actor: str
    at: str
