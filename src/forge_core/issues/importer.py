"""Importa issues concluídas via gh (sessão local). Somente leitura. Sem token no env."""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from ..config import Settings
from ..draft.github_gh import DraftError, GhCli
from ..errors import ForgeError
from ..redaction import redact_secrets
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository
from .notes import write_issue_note
from .store import CompletedIssue, upsert

log = logging.getLogger("forge_core.issues")

PER_REPO_LIMIT = 50
BOARD_LIMIT = 100
MAX_TOTAL = 80
MAX_BODY_BYTES = 64 * 1024


class IssueImportError(ForgeError):
    """Falha curta do importador. Código fixo; sem corpo de issue nem stdout do gh."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


class CompletedIssueImporter:
    def __init__(
        self,
        repo: SqlRepository,
        settings: Settings,
        *,
        gh: GhCli | None = None,
        clock: Callable[[], str] | None = None,
    ):
        self._repo = repo
        self._settings = settings
        self._gh = gh
        self._clock = clock
        self._lock = threading.Lock()
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def run(self, *, reason: str = "poll", actor: str = "system:poll") -> dict:
        """Importa issues fechadas e/ou na coluna Done. Idempotente. Sem escrita no GitHub."""
        if not self._lock.acquire(blocking=False):
            raise IssueImportError("busy")
        self._busy = True
        log.info("issues.import reason=%s", reason)
        try:
            if self._gh is None:
                raise IssueImportError("gh_missing")
            allowed = {
                f"{row.owner}/{row.repo_name}": row
                for row in list_active_allowed_repos(self._repo)
            }
            if not allowed:
                return {"imported": 0, "updated": 0, "repos": []}
            keys = self._collect_keys(allowed)
            imported = 0
            updated = 0
            errors = 0
            for repo_name, number, meta in keys[:MAX_TOTAL]:
                try:
                    existed = self._exists(repo_name, number)
                    item = self._fetch_one(repo_name, number, meta)
                    upsert(self._repo, {
                        "repo": item.repo,
                        "number": item.number,
                        "title": item.title,
                        "body": item.body,
                        "labels": item.labels,
                        "prs": item.prs,
                        "closed_at": item.closed_at,
                        "url": item.url,
                    }, imported_at=self._now())
                    write_issue_note(self._settings, item)
                    digest = hashlib.sha256(item.body.encode("utf-8")).hexdigest()[:16]
                    log.info(
                        "issues.import repo=%s number=%s bytes=%s hash=%s result=ok",
                        item.repo, item.number, len(item.body.encode("utf-8")), digest,
                    )
                    if existed:
                        updated += 1
                    else:
                        imported += 1
                except IssueImportError as exc:
                    errors += 1
                    log.info(
                        "issues.import repo=%s number=%s result=error:%s",
                        repo_name, number, exc.code,
                    )
                except DraftError as exc:
                    errors += 1
                    log.info(
                        "issues.import repo=%s number=%s result=error:%s",
                        repo_name, number, exc.code,
                    )
            result = {"imported": imported, "updated": updated, "errors": errors, "repos": list(allowed)}
            self._repo.record_audit(
                actor, "issues.import", "repos:*",
                f"ok: reason={reason} imported={imported} updated={updated} errors={errors}",
            )
            return result
        except DraftError as exc:
            code = exc.code if exc.code in {"gh_missing", "gh_not_logged", "gh_error", "timeout"} else "gh_error"
            log.info("issues.import reason=%s result=error:%s", reason, code)
            raise IssueImportError(code) from exc
        finally:
            self._busy = False
            self._lock.release()

    def _collect_keys(self, allowed: dict) -> list[tuple[str, int, dict]]:
        seen: dict[tuple[str, int], dict] = {}
        for full in allowed:
            try:
                for item in self._gh.list_closed_issues(full, limit=PER_REPO_LIMIT):
                    key = (str(item["repo"]), int(item["number"]))
                    seen[key] = item
            except DraftError as exc:
                log.info("issues.import repo=%s result=error:%s", full, exc.code)
        try:
            for item in self._gh.list_done_project_issues(set(allowed), limit=BOARD_LIMIT):
                key = (str(item["repo"]), int(item["number"]))
                prev = seen.get(key) or {}
                merged = {**prev, **item}
                seen[key] = merged
        except DraftError as exc:
            log.info("issues.import board result=error:%s", exc.code)
        out = [(repo, number, meta) for (repo, number), meta in seen.items() if repo in allowed]
        out.sort(key=lambda row: (row[0], -row[1]))
        return out

    def _fetch_one(self, repo: str, number: int, meta: dict) -> CompletedIssue:
        detail = self._gh.view_completed_issue(repo, number)
        body = redact_secrets(detail.get("body") or "")
        encoded = body.encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            body = encoded[:MAX_BODY_BYTES].decode("utf-8", "ignore")
        title = redact_secrets(detail.get("title") or meta.get("title") or "")
        labels = {
            "tipo": str(detail.get("tipo") or meta.get("tipo") or ""),
            "prioridade": str(detail.get("prioridade") or meta.get("prioridade") or ""),
            "sprint": str(detail.get("sprint") or meta.get("sprint") or ""),
            "names": [str(n) for n in (detail.get("labels") or meta.get("labels") or []) if str(n).strip()],
        }
        prs = detail.get("prs") or []
        if not isinstance(prs, list):
            prs = []
        return CompletedIssue(
            repo=str(detail.get("repo") or repo),
            number=int(detail.get("number") or number),
            title=title,
            body=body,
            labels=labels,
            prs=prs,
            closed_at=detail.get("closed_at") or meta.get("closed_at"),
            url=str(detail.get("url") or meta.get("url") or ""),
            imported_at=self._now(),
        )

    def _exists(self, repo: str, number: int) -> bool:
        rows = self._repo.fetch(
            "SELECT 1 FROM completed_issues WHERE lower(repo) = lower(?) AND number = ?",
            (repo, int(number)),
        )
        return bool(rows)

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock()
        return datetime.now(timezone.utc).isoformat()
