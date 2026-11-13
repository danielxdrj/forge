"""Rotas /api/investigations: investigação livre (sem issue obrigatória), somente leitura."""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError, DraftError
from ..investigations.service import InvestigationRuleError, InvestigationService


def register_investigation_routes(
    app: FastAPI,
    investigations: InvestigationService,
    *,
    json_error,
    need_editor_or_owner,
    panel=None,
):
    def _rule(exc: InvestigationRuleError) -> JSONResponse:
        status = {
            "not_found": 404,
            "provider_missing": 503,
            "claude_cli_missing": 503,
            "cursor_cli_missing": 503,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    def _draft_rule(exc: DraftError) -> JSONResponse:
        status = {
            "provider_missing": 503,
            "claude_cli_missing": 503,
            "cursor_cli_missing": 503,
            "claude_cli_error": 502,
            "provider_error": 502,
            "repo_not_allowed": 400,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.post("/api/investigations/run")
    async def api_run_investigation(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            view = investigations.run(principal, body)
        except InvestigationRuleError as exc:
            return _rule(exc)
        except DraftError as exc:
            return _draft_rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json()

    @app.get("/api/investigations")
    def api_list_investigations(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            items = investigations.list_investigations(principal)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"investigations": [i.as_json() for i in items]}

    @app.get("/api/investigations/{investigation_id}")
    def api_get_investigation(request: Request, investigation_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            view = investigations.get_investigation(principal, investigation_id)
        except InvestigationRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return view.as_json()

    @app.post("/api/investigations/{investigation_id}/to-task")
    async def api_investigation_to_task(request: Request, investigation_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        if panel is None:
            return json_error(503, "provider_missing")
        try:
            view = investigations.get_investigation(principal, investigation_id)
        except InvestigationRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        repo_name = str(body.get("repo") or "").strip() or (view.repos[0] if view.repos else "")
        if not repo_name:
            return json_error(400, "repo_required")
        context = _task_context(view)
        try:
            result = panel.generate(principal, repo_name, context)
        except DraftError as exc:
            return _draft_rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return result


def _task_context(view) -> str:
    parts = [view.description.strip()]
    if view.result.strip():
        parts.append("## Achados da investigação\n" + view.result.strip())
    return "\n\n".join(p for p in parts if p).strip()
