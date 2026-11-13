"""Rota /api/issues/{owner}/{repo}/{number}/delete: owner, confirmação exata."""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError
from ..issues.delete import IssueDeleteError, IssueDeleteService


def register_issue_delete_routes(
    app: FastAPI,
    svc: IssueDeleteService,
    *,
    json_error,
    need_owner,
):
    def _rule(exc: IssueDeleteError) -> JSONResponse:
        status = {
            "confirm_mismatch": 400,
            "invalid_issue": 400,
            "gh_missing": 503,
            "gh_not_logged": 503,
            "issue_delete_forbidden": 403,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.post("/api/issues/{owner}/{repo}/{number}/delete")
    async def api_delete_issue(request: Request, owner: str, repo: str, number: int):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        confirm = str(body.get("confirm") or "")
        fallback = body.get("fallback")
        fallback = str(fallback) if isinstance(fallback, str) else None
        purge_notes = bool(body.get("purge_notes"))
        try:
            result = svc.delete(
                principal, owner, repo, number, confirm,
                fallback=fallback, purge_notes=purge_notes,
            )
        except IssueDeleteError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"status": "ok", "repo": result.repo, "number": result.number, "mode": result.mode}
