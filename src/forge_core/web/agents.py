"""Rotas /api/agents: catálogo e governança da aba "Agentes" (CRUD + métricas + aprovação)."""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..agent_catalog.service import AgentCatalogService, AgentRuleError
from ..errors import AuthorizationError


def register_agent_catalog_routes(
    app: FastAPI,
    agents: AgentCatalogService,
    *,
    json_error,
    need_editor_or_owner,
    need_owner,
):
    def _rule(exc: AgentRuleError) -> JSONResponse:
        status = {
            "not_found": 404,
            "name_taken": 409,
            "already_decided": 409,
            "write_denied_resource": 400,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/agents")
    def api_list_agents(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return agents.list_agents(principal)
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.post("/api/agents")
    async def api_create_agent(request: Request):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            view = agents.create(principal, body)
        except AgentRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json()

    @app.get("/api/agents/approvals")
    def api_list_agent_approvals(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            items = agents.list_approvals(principal)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"approvals": [a.as_json() for a in items]}

    @app.get("/api/agents/{agent_id}")
    def api_get_agent(request: Request, agent_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return agents.get_agent(principal, agent_id)
        except AgentRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.post("/api/agents/{agent_id}")
    async def api_update_agent(request: Request, agent_id: str):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            view = agents.update(principal, agent_id, body)
        except AgentRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json()

    @app.post("/api/agents/approvals/{approval_id}/approve")
    def api_approve_agent_approval(request: Request, approval_id: str):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            view = agents.decide_approval(principal, approval_id, "approved")
        except AgentRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return view.as_json()

    @app.post("/api/agents/approvals/{approval_id}/reject")
    def api_reject_agent_approval(request: Request, approval_id: str):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            view = agents.decide_approval(principal, approval_id, "rejected")
        except AgentRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return view.as_json()
