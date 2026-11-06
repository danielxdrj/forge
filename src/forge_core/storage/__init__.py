"""Persistência do Core (ADR-004): repositório, migrações e auditoria append-only."""
from .repository import AuditEntry, Repository, Task, TaskEvent
from .sql import SqlRepository, migrate_database, open_repository

__all__ = ["AuditEntry", "Repository", "Task", "TaskEvent", "SqlRepository", "migrate_database", "open_repository"]
