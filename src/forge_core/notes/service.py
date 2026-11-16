"""CRUD de notas manuais por issue. O corpo não entra em log nem em audit_log."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from ..auth.store import AuthStore, Principal
from ..errors import AuthorizationError, ForgeError
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository

MAX_TITLE = 200
MAX_BODY_BYTES = 64 * 1024
ISSUE_KEY = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#\d{1,10}$")


class NoteRuleError(ForgeError):
    """Validação da nota. Código fixo; nunca inclui o corpo."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class NoteView:
    id: str
    issue_key: str | None
    title: str
    body: str
    created_by: str
    created_at: str
    updated_at: str

    @property
    def size(self) -> int:
        return len(self.body.encode("utf-8"))

    def as_json(self, *, include_body: bool) -> dict:
        data = {
            "id": self.id,
            "issue_key": self.issue_key,
            "title": self.title,
            "size": self.size,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_body:
            data["body"] = self.body
        return data


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_editor_or_owner(store: AuthStore, principal: Principal) -> Principal:
    store.require_session(principal)
    ident = principal.identity_id
    if store.has_role(ident, "editor") or store.has_role(ident, "owner"):
        return principal
    store._repo.record_audit(ident, "auth.denied", "role:note_editor", "error: forbidden")
    raise AuthorizationError("forbidden")


def allowed_issue_repos(repo: SqlRepository) -> set[str]:
    return {f"{row.owner}/{row.repo_name}".lower() for row in list_active_allowed_repos(repo)}


def parse_issue_key(raw: str) -> str:
    key = (raw or "").strip()
    if not ISSUE_KEY.fullmatch(key):
        raise NoteRuleError("invalid_issue")
    return key


def _require_allowed_issue(repo: SqlRepository, issue_key: str) -> str:
    key = parse_issue_key(issue_key)
    repo_name, _sep, _num = key.partition("#")
    if repo_name.lower() not in allowed_issue_repos(repo):
        raise NoteRuleError("repo_not_allowed")
    return key


class NoteService:
    def __init__(self, repo: SqlRepository, store: AuthStore):
        self._repo = repo
        self._store = store

    def list_notes(self, principal: Principal, issue_key: str | None = None) -> list[NoteView]:
        _require_editor_or_owner(self._store, principal)
        if issue_key:
            key = parse_issue_key(issue_key)
            rows = self._repo.fetch(
                "SELECT id, issue_key, title, body, created_by, created_at, updated_at "
                "FROM investigation_notes WHERE kind = 'note' AND issue_key = ? "
                "ORDER BY updated_at DESC, id",
                (key,),
            )
        else:
            rows = self._repo.fetch(
                "SELECT id, issue_key, title, body, created_by, created_at, updated_at "
                "FROM investigation_notes WHERE kind = 'note' ORDER BY updated_at DESC, id",
            )
        return [NoteView(*row) for row in rows]

    def get_note(self, principal: Principal, note_id: str) -> NoteView:
        _require_editor_or_owner(self._store, principal)
        view = self._load(note_id)
        if view is None:
            raise NoteRuleError("not_found")
        return view

    def create(self, principal: Principal, payload: dict) -> NoteView:
        _require_editor_or_owner(self._store, principal)
        raw_issue = str(payload.get("issue_key") or "").strip()
        issue_key = _require_allowed_issue(self._repo, raw_issue) if raw_issue else None
        title = _title(payload.get("title"))
        body = _body(payload.get("body"))
        note_id = str(uuid.uuid4())
        ts = _now()
        size = len(body.encode("utf-8"))
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO investigation_notes "
                "(id, issue_key, title, body, created_by, created_at, updated_at, kind) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'note')",
                (note_id, issue_key, title, body, principal.identity_id, ts, ts),
            )
            tx.audit(
                principal.identity_id, "note.create", f"note:{note_id}", f"ok: bytes={size}",
            )
        view = self._load(note_id)
        if view is None:
            raise NoteRuleError("not_found")
        return view

    def update(self, principal: Principal, note_id: str, payload: dict) -> NoteView:
        _require_editor_or_owner(self._store, principal)
        current = self._load(note_id)
        if current is None:
            raise NoteRuleError("not_found")
        title = _title(payload.get("title") if "title" in payload else current.title)
        body = _body(payload.get("body") if "body" in payload else current.body)
        size = len(body.encode("utf-8"))
        ts = _now()
        with self._repo.transaction() as tx:
            tx.execute(
                "UPDATE investigation_notes SET title=?, body=?, updated_at=? WHERE id=?",
                (title, body, ts, note_id),
            )
            tx.audit(
                principal.identity_id, "note.update", f"note:{note_id}", f"ok: bytes={size}",
            )
        view = self._load(note_id)
        if view is None:
            raise NoteRuleError("not_found")
        return view

    def delete(self, principal: Principal, note_id: str) -> None:
        _require_editor_or_owner(self._store, principal)
        current = self._load(note_id)
        if current is None:
            raise NoteRuleError("not_found")
        size = current.size
        with self._repo.transaction() as tx:
            tx.execute("DELETE FROM investigation_notes WHERE id=?", (note_id,))
            tx.audit(
                principal.identity_id, "note.delete", f"note:{note_id}", f"ok: bytes={size}",
            )

    def _load(self, note_id: str) -> NoteView | None:
        rows = self._repo.fetch(
            "SELECT id, issue_key, title, body, created_by, created_at, updated_at "
            "FROM investigation_notes WHERE kind = 'note' AND id = ?",
            (note_id,),
        )
        if not rows:
            return None
        return NoteView(*rows[0])


def _title(raw) -> str:
    if raw is None:
        raise NoteRuleError("invalid_title")
    if not isinstance(raw, str):
        raise NoteRuleError("invalid_title")
    title = raw.strip()
    if not title or len(title) > MAX_TITLE:
        raise NoteRuleError("invalid_title")
    return title


def _body(raw) -> str:
    if raw is None:
        raise NoteRuleError("invalid_body")
    if not isinstance(raw, str):
        raise NoteRuleError("invalid_body")
    body = raw.replace("\x00", "")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise NoteRuleError("body_too_large")
    return body
