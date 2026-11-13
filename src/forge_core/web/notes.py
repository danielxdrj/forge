"""Rotas /api/notes e /api/issues. CSRF no middleware; editor ou owner."""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..draft.github_gh import DraftError, GhCli
from ..errors import AuthorizationError
from ..notes.service import NoteRuleError, NoteService
from ..storage.seed import list_active_allowed_repos


def register_note_routes(
    app: FastAPI,
    notes: NoteService,
    *,
    json_error,
    need_editor_or_owner,
    gh: GhCli | None = None,
):
    def _rule(exc: NoteRuleError) -> JSONResponse:
        status = {"not_found": 404}.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/issues")
    def api_list_issues(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        issues, error = _collect_issues(app.state.repo, gh)
        payload = {"issues": issues}
        if error:
            payload["error"] = error
        return payload

    @app.get("/api/notes")
    def api_list_notes(request: Request, issue: str | None = None):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            items = notes.list_notes(principal, issue)
        except NoteRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"notes": [n.as_json(include_body=False) for n in items]}

    @app.get("/api/notes/{note_id}")
    def api_get_note(request: Request, note_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            view = notes.get_note(principal, note_id)
        except NoteRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return view.as_json(include_body=True)

    @app.post("/api/notes")
    async def api_create_note(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            view = notes.create(principal, body)
        except NoteRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json(include_body=True)

    @app.post("/api/notes/{note_id}")
    async def api_update_note(request: Request, note_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            view = notes.update(principal, note_id, body)
        except NoteRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json(include_body=True)

    @app.post("/api/notes/{note_id}/delete")
    def api_delete_note(request: Request, note_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            notes.delete(principal, note_id)
        except NoteRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"status": "ok"}


def _collect_issues(repo, gh: GhCli | None) -> tuple[list[dict], str | None]:
    seen: dict[str, dict] = {}
    error = None
    if gh is not None:
        try:
            for row in list_active_allowed_repos(repo):
                full = f"{row.owner}/{row.repo_name}"
                for issue in gh.list_issues(full):
                    key = f"{full}#{issue.number}"
                    seen[key] = {
                        "issue_key": key,
                        "repo": full,
                        "number": issue.number,
                        "title": issue.title or "",
                        "url": issue.url or "",
                        "state": issue.state or "",
                    }
        except DraftError as exc:
            error = exc.code
    for row in repo.fetch(
        "SELECT issue_key, title FROM investigation_notes WHERE kind = 'note' "
        "ORDER BY updated_at DESC, id"
    ):
        key = row[0]
        if not key:
            continue
        if key in seen:
            continue
        repo_name, _sep, number = key.partition("#")
        try:
            num = int(number)
        except ValueError:
            continue
        seen[key] = {
            "issue_key": key,
            "repo": repo_name,
            "number": num,
            "title": row[1] or "",
            "url": "",
            "state": "",
        }
    issues = sorted(seen.values(), key=lambda i: (i["repo"], -int(i["number"])))
    return issues, error
