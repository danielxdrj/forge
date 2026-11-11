"""Casos de uso da tela de tarefas (ADR-017 PR B). Fakes nos testes; Cursor CLI + gh no container."""
from __future__ import annotations

import hashlib
import tempfile
import uuid
from pathlib import Path

from ..auth.store import Principal
from ..draft.context import decode_utf8
from ..draft.github_gh import GhCli, RemoteState, canonical_board_value, find_field
from ..draft.service import DraftResult, DraftService, parse_model_json_from_body, parse_remote
from ..draft.template import PENDING, required_pending, validate_repo
from ..errors import DraftError
from ..storage.drafts import (
    DraftRecord,
    ensure_task_link,
    insert_draft,
    latest_draft_for_task,
    link_of_kind,
    list_all_drafts,
    list_task_links,
    update_draft,
)
from ..storage.seed import list_active_allowed_repos
from ..tasks.service import TaskService


def preview_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def allowed_full_names(repo) -> set[str]:
    return {f"{row.owner}/{row.repo_name}".lower() for row in list_active_allowed_repos(repo)}


def require_allowed_repo(store_repo, repo_name: str) -> str:
    repo_name = validate_repo(repo_name)
    if repo_name.lower() not in allowed_full_names(store_repo):
        raise DraftError("repo_not_allowed")
    return repo_name


class BoardFieldCache:
    def __init__(self, gh: GhCli | None, ttl: float = 60.0, monotonic=None):
        self._gh = gh
        self._ttl = ttl
        self._clock = monotonic
        self._at = 0.0
        self._data: dict | None = None

    def get(self) -> dict:
        if self._gh is None:
            raise DraftError("gh_missing")
        import time

        now = (self._clock or time.monotonic)()
        if self._data is not None and now - self._at < self._ttl:
            return self._data
        self._gh.preflight()
        fields = self._gh.list_fields()
        data = {}
        for key in ("tipo", "prioridade", "size"):
            field = find_field(fields, key)
            names = []
            for opt in field.get("options") or []:
                name = str(opt.get("name") or "").strip()
                if name:
                    names.append(name)
            data[key] = names
        self._data = data
        self._at = now
        return data


class WebTaskService:
    def __init__(
        self,
        repo,
        tasks: TaskService,
        provider,
        gh: GhCli | None,
        *,
        drafts_dir: Path | None = None,
        field_cache: BoardFieldCache | None = None,
    ):
        self.repo = repo
        self.tasks = tasks
        self.gh = gh
        self.provider = provider
        self.drafts_dir = Path(drafts_dir) if drafts_dir else Path(tempfile.mkdtemp(prefix="forge-web-drafts-"))
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.fields = field_cache or BoardFieldCache(gh)
        self.drafts = DraftService(tasks, provider, gh)

    def list_repos(self, principal: Principal) -> list[dict]:
        self.tasks._auth.require(principal, "editor")
        rows = list_active_allowed_repos(self.repo)
        return [{"owner": r.owner, "name": r.repo_name, "full_name": f"{r.owner}/{r.repo_name}"} for r in rows]

    def board_fields(self, principal: Principal) -> dict:
        self.tasks._auth.require(principal, "editor")
        return self.fields.get()

    def generate(self, principal: Principal, repo_name: str, context: str) -> dict:
        self.tasks._auth.require(principal, "editor")
        if self.provider is None:
            raise DraftError("provider_missing")
        repo_name = require_allowed_repo(self.repo, repo_name)
        text = decode_utf8(context.encode("utf-8"), origin="contexto")
        output = self.drafts_dir / f"draft-{uuid.uuid4().hex}.md"
        board = self._board_or_empty()
        meta = {"tipo": "", "prioridade": "", "size": "", "sprint": "", "escopo": ""}
        result = self.drafts.generate(text, repo_name, principal, output, meta, board=board)
        meta = {
            "tipo": (result.meta or {}).get("tipo") or "",
            "prioridade": (result.meta or {}).get("prioridade") or "",
            "size": (result.meta or {}).get("size") or "",
            "sprint": "",
            "escopo": "",
        }
        preview = self.drafts.preview_text(result, repo_name, meta, result.branch_prefix)
        digest = preview_hash(preview)
        rec = insert_draft(
            self.repo,
            task_id=result.task_id,
            repo_name=repo_name,
            body_md=result.body,
            tipo=meta["tipo"],
            prioridade=meta["prioridade"],
            size=meta["size"],
            preview_hash=digest,
            created_by=principal.identity_id,
            status="rascunho",
        )
        self.repo.record_audit(
            principal.identity_id, "draft.generate", f"task:{result.task_id}", f"ok: repo={repo_name} hash={digest}"
        )
        pending = required_pending(parse_model_json_from_body(result.body), meta)
        return {
            "task_id": result.task_id,
            "draft_id": rec.id,
            "title": result.title,
            "body": result.body,
            "preview": preview,
            "preview_hash": digest,
            "repo": repo_name,
            "tipo": rec.tipo,
            "prioridade": rec.prioridade,
            "size": rec.size,
            "pending": pending,
        }

    def update_fields(
        self,
        principal: Principal,
        task_id: str,
        tipo: str,
        prioridade: str,
        size: str,
        body_md: str | None = None,
    ) -> dict:
        self.tasks._auth.require(principal, "editor")
        draft = latest_draft_for_task(self.repo, task_id)
        if draft is None:
            raise DraftError("draft_missing")
        if draft.status == "publicado":
            raise DraftError("draft_published")
        if draft.status == "cancelado":
            raise DraftError("draft_cancelled")
        next_body = draft.body_md
        if body_md is not None:
            next_body = decode_utf8(body_md.encode("utf-8"), origin="rascunho")
        parsed = parse_model_json_from_body(next_body)
        options = self._board_or_none()
        meta = {
            "tipo": self._canonical_field("tipo", tipo, options),
            "prioridade": self._canonical_field("prioridade", prioridade, options),
            "size": self._canonical_field("size", size, options),
            "sprint": "",
            "escopo": "",
        }
        result = self._result_from_body(draft, principal, next_body, parsed["title"])
        preview = self.drafts.preview_text(result, draft.repo, meta, result.branch_prefix)
        digest = preview_hash(preview)
        rec = update_draft(
            self.repo, draft.id,
            tipo=meta["tipo"], prioridade=meta["prioridade"], size=meta["size"],
            preview_hash=digest, body_md=next_body,
        )
        self.repo.record_audit(
            principal.identity_id, "draft.fields", f"task:{task_id}", f"ok: repo={draft.repo} hash={digest}"
        )
        pending = required_pending(parsed, meta)
        return {
            "task_id": task_id,
            "draft_id": rec.id,
            "title": parsed["title"],
            "body": rec.body_md,
            "preview": preview,
            "preview_hash": digest,
            "tipo": rec.tipo,
            "prioridade": rec.prioridade,
            "size": rec.size,
            "pending": pending,
        }

    def confirm(self, principal: Principal, task_id: str, submitted_hash: str) -> dict:
        self.tasks._auth.require(principal, "editor")
        if self.gh is None:
            raise DraftError("gh_missing")
        draft = latest_draft_for_task(self.repo, task_id)
        if draft is None:
            raise DraftError("draft_missing")
        if submitted_hash != draft.preview_hash:
            raise DraftError("diff_changed")
        if draft.status == "publicado":
            return self._payload_from_links(task_id, draft, status="publicado")
        if draft.status == "cancelado":
            raise DraftError("draft_cancelled")
        meta = {
            "tipo": draft.tipo, "prioridade": draft.prioridade, "size": draft.size,
            "sprint": "", "escopo": "",
        }
        result = self._result_from_draft(draft, principal)
        pending = required_pending(parse_model_json_from_body(result.body), meta)
        if pending:
            raise DraftError("pending_fields", fields=pending)
        if draft.status == "rascunho":
            draft = update_draft(self.repo, draft.id, status="confirmado")
        try:
            published = self.drafts.publish(result, draft.repo, principal, meta, result.branch_prefix)
        except DraftError:
            self._sync_links(task_id, draft.repo, principal)
            raise
        self._sync_links(task_id, draft.repo, principal, published.remote)
        update_draft(self.repo, draft.id, status="publicado")
        issue_url = published.remote.url or ""
        self.repo.record_audit(
            principal.identity_id,
            "draft.confirm",
            f"task:{task_id}",
            f"ok: repo={draft.repo} hash={draft.preview_hash} issue={issue_url}",
        )
        return self._payload_from_links(task_id, draft, status="publicado")

    def discard(self, principal: Principal, task_id: str) -> dict:
        """Marca o rascunho como cancelado. Não apaga linhas. Idempotente se já cancelado."""
        self.tasks._auth.require(principal, "editor")
        draft = latest_draft_for_task(self.repo, task_id)
        if draft is None:
            raise DraftError("draft_missing")
        if draft.status == "cancelado":
            return {
                "task_id": task_id,
                "draft_id": draft.id,
                "status": "cancelado",
            }
        if draft.status == "publicado":
            raise DraftError("draft_published")
        links = list_task_links(self.repo, task_id)
        if link_of_kind(links, "issue"):
            raise DraftError("draft_published")
        rec = update_draft(self.repo, draft.id, status="cancelado")
        self.repo.record_audit(
            principal.identity_id, "draft.discard", f"task:{task_id}",
            f"ok: repo={draft.repo} status=cancelado",
        )
        return {
            "task_id": task_id,
            "draft_id": rec.id,
            "status": rec.status,
        }

    def list_tasks(self, principal: Principal) -> dict:
        self.tasks._auth.require(principal, "editor")
        seen: set[str] = set()
        published: list[dict] = []
        drafts: list[dict] = []
        for draft in reversed(list_all_drafts(self.repo)):
            if draft.task_id in seen:
                continue
            seen.add(draft.task_id)
            if draft.status == "cancelado":
                continue
            task = self.tasks.get_task(draft.task_id)
            if task is None:
                continue
            self._maybe_store_pr(draft, principal)
            links = list_task_links(self.repo, draft.task_id)
            issue = link_of_kind(links, "issue")
            pr = link_of_kind(links, "pr")
            branch = link_of_kind(links, "branch")
            item = {
                "id": task.id,
                "repo": draft.repo,
                "title": task.title,
                "status": task.status,
                "draft_status": draft.status,
                "issue_url": issue.url if issue else None,
                "pr_url": pr.url if pr else None,
                "branch": _branch_from_link(branch),
                "board_item_id": issue.board_item_id if issue else None,
            }
            if item["issue_url"]:
                published.append(item)
            else:
                drafts.append(item)
        return {
            "published": published,
            "drafts": drafts,
            "tasks": published + drafts,
        }

    def _board_or_empty(self) -> dict:
        try:
            return self.fields.get()
        except DraftError:
            return {}

    def _board_or_none(self) -> dict | None:
        try:
            return self.fields.get()
        except DraftError:
            return None

    def _canonical_field(self, key: str, value: str, options: dict | None) -> str:
        text = (value or "").strip()
        if not text or text.lower() == PENDING.lower():
            return ""
        if options is None:
            return text
        names = list(options.get(key) or [])
        matched = canonical_board_value(names, text)
        if matched is None:
            raise DraftError("invalid_board_option", fields=[key])
        return matched

    def _result_from_draft(self, draft: DraftRecord, principal: Principal) -> DraftResult:
        return self._result_from_body(draft, principal, draft.body_md)

    def _result_from_body(
        self, draft: DraftRecord, principal: Principal, body: str, title: str | None = None,
    ) -> DraftResult:
        path = self._materialize_body(draft.task_id, body)
        result = self.drafts.load_resume(draft.task_id, path, principal, draft.repo)
        if title:
            result.title = title
        else:
            parsed = parse_model_json_from_body(body)
            result.title = parsed["title"]
        result.body = body
        return result

    def _materialize_body(self, task_id: str, body: str) -> Path:
        path = self.drafts_dir / f"{task_id}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def _materialize(self, draft: DraftRecord) -> Path:
        return self._materialize_body(draft.task_id, draft.body_md)

    def _sync_links(self, task_id: str, repo_name: str, principal: Principal, remote: RemoteState | None = None):
        if remote is None:
            task = self.tasks.get_task(task_id)
            remote = parse_remote(task.context) if task else RemoteState(repo=repo_name)
        if remote.url:
            ensure_task_link(
                self.repo,
                task_id=task_id,
                kind="issue",
                repo_name=repo_name,
                url=remote.url,
                number=remote.issue,
                board_item_id=remote.item_id,
            )
        if remote.branch:
            branch_url = f"https://github.com/{repo_name}/tree/{remote.branch}"
            ensure_task_link(
                self.repo,
                task_id=task_id,
                kind="branch",
                repo_name=repo_name,
                url=branch_url,
            )

    def _maybe_store_pr(self, draft: DraftRecord, principal: Principal) -> None:
        links = list_task_links(self.repo, draft.task_id)
        if link_of_kind(links, "pr"):
            return
        branch = link_of_kind(links, "branch")
        if branch is None or self.gh is None:
            return
        head = _branch_from_link(branch)
        if not head:
            return
        url = self.gh.find_pr(draft.repo, head)
        if url:
            ensure_task_link(
                self.repo, task_id=draft.task_id, kind="pr", repo_name=draft.repo, url=url,
            )

    def _payload_from_links(self, task_id: str, draft: DraftRecord, *, status: str) -> dict:
        links = list_task_links(self.repo, task_id)
        issue = link_of_kind(links, "issue")
        pr = link_of_kind(links, "pr")
        branch = link_of_kind(links, "branch")
        return {
            "task_id": task_id,
            "status": status,
            "repo": draft.repo,
            "issue_url": issue.url if issue else None,
            "pr_url": pr.url if pr else None,
            "branch": _branch_from_link(branch),
            "board_item_id": issue.board_item_id if issue else None,
        }


def _branch_from_link(link) -> str | None:
    if link is None:
        return None
    url = link.url or ""
    marker = "/tree/"
    if marker in url:
        return url.split(marker, 1)[1]
    return url or None
