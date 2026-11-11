"""Helpers de persistência de rascunhos e vínculos de tarefa (ADR-017). Sem UI nesta entrega."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..errors import ForgeError
from .sql import SqlRepository

DRAFT_STATUSES = ("rascunho", "confirmado", "publicado", "cancelado")
LINK_KINDS = ("issue", "pr", "branch")


class DraftStorageError(ForgeError):
    """Dado de rascunho ou vínculo recusado. Mensagem fixa; sem corpo livre."""


@dataclass(frozen=True)
class DraftRecord:
    id: str
    task_id: str
    repo: str
    body_md: str
    tipo: str
    prioridade: str
    size: str
    preview_hash: str
    status: str
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TaskLinkRecord:
    id: str
    task_id: str
    kind: str
    repo: str
    number: int | None
    url: str
    board_item_id: str | None
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_draft(r) -> DraftRecord:
    return DraftRecord(*r)


def _row_link(r) -> TaskLinkRecord:
    return TaskLinkRecord(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])


def insert_draft(
    repo: SqlRepository,
    *,
    task_id: str,
    repo_name: str,
    body_md: str,
    tipo: str,
    prioridade: str,
    size: str,
    preview_hash: str,
    created_by: str,
    status: str = "rascunho",
    draft_id: str | None = None,
    now: str | None = None,
) -> DraftRecord:
    if status not in DRAFT_STATUSES:
        raise DraftStorageError("invalid_draft_status")
    ts = now or _now()
    did = draft_id or str(uuid.uuid4())
    repo._run(
        [
            (
                "INSERT INTO drafts (id, task_id, repo, body_md, tipo, prioridade, size, preview_hash, "
                "status, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (did, task_id, repo_name, body_md, tipo, prioridade, size, preview_hash, status,
                 created_by, ts, ts),
            )
        ]
    )
    return get_draft(repo, did)


def get_draft(repo: SqlRepository, draft_id: str) -> DraftRecord:
    rows = repo.fetch(
        "SELECT id, task_id, repo, body_md, tipo, prioridade, size, preview_hash, status, created_by, "
        "created_at, updated_at FROM drafts WHERE id = ?",
        (draft_id,),
    )
    if len(rows) != 1:
        raise DraftStorageError("draft_missing")
    return _row_draft(rows[0])


def list_drafts_for_task(repo: SqlRepository, task_id: str) -> list[DraftRecord]:
    rows = repo.fetch(
        "SELECT id, task_id, repo, body_md, tipo, prioridade, size, preview_hash, status, created_by, "
        "created_at, updated_at FROM drafts WHERE task_id = ? ORDER BY created_at, id",
        (task_id,),
    )
    return [_row_draft(r) for r in rows]


def insert_task_link(
    repo: SqlRepository,
    *,
    task_id: str,
    kind: str,
    repo_name: str,
    url: str,
    number: int | None = None,
    board_item_id: str | None = None,
    link_id: str | None = None,
    now: str | None = None,
) -> TaskLinkRecord:
    if kind not in LINK_KINDS:
        raise DraftStorageError("invalid_link_kind")
    ts = now or _now()
    lid = link_id or str(uuid.uuid4())
    repo._run(
        [
            (
                "INSERT INTO task_links (id, task_id, kind, repo, number, url, board_item_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lid, task_id, kind, repo_name, number, url, board_item_id, ts),
            )
        ]
    )
    return get_task_link(repo, lid)


def get_task_link(repo: SqlRepository, link_id: str) -> TaskLinkRecord:
    rows = repo.fetch(
        "SELECT id, task_id, kind, repo, number, url, board_item_id, created_at FROM task_links WHERE id = ?",
        (link_id,),
    )
    if len(rows) != 1:
        raise DraftStorageError("task_link_missing")
    return _row_link(rows[0])


def list_task_links(repo: SqlRepository, task_id: str) -> list[TaskLinkRecord]:
    rows = repo.fetch(
        "SELECT id, task_id, kind, repo, number, url, board_item_id, created_at FROM task_links "
        "WHERE task_id = ? ORDER BY created_at, id",
        (task_id,),
    )
    return [_row_link(r) for r in rows]
