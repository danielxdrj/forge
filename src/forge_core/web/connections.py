"""Rotas /api/connections. O front só fala com a API; o segredo nunca volta no JSON."""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..connections.service import ConnectionRuleError, ConnectionService
from ..errors import AuthorizationError


def _pop_secret(body: dict) -> str | None:
    if not isinstance(body, dict):
        return None
    secret = body.pop("secret", None)
    if secret is None:
        return None
    if not isinstance(secret, str):
        raise ConnectionRuleError("invalid_secret")
    if len(secret) > 8192:
        raise ConnectionRuleError("invalid_secret")
    secret = secret.strip("\r\n")
    return secret or None


def register_connection_routes(
    app: FastAPI,
    svc: ConnectionService,
    *,
    json_error,
    need_principal,
    need_owner,
    need_reader,
):
    def _rule(exc: ConnectionRuleError) -> JSONResponse:
        status = {
            "not_found": 404,
            "vault_disabled": 503,
            "vault_invalid": 503,
            "vault_unavailable": 503,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/connections")
    def api_list_connections(request: Request):
        principal = need_reader(request)
        if isinstance(principal, JSONResponse):
            return principal
        status = svc.status()
        if not status["enabled"]:
            return status
        try:
            items = svc.list_connections(principal)
        except ConnectionRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"enabled": True, "connections": [c.as_json() for c in items]}

    @app.get("/api/connections/{connection_id}")
    def api_get_connection(request: Request, connection_id: str):
        principal = need_reader(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            view = svc.get_connection(principal, connection_id)
        except ConnectionRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return view.as_json()

    @app.post("/api/connections")
    async def api_create_connection(request: Request):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            secret = _pop_secret(body)
            view = svc.create(principal, body, secret)
        except ConnectionRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json()

    @app.post("/api/connections/{connection_id}")
    async def api_update_connection(request: Request, connection_id: str):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return json_error(400, "invalid_json")
            secret = _pop_secret(body)
            view = svc.update(principal, connection_id, body, secret)
        except ConnectionRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        return view.as_json()

    @app.post("/api/connections/{connection_id}/delete")
    def api_delete_connection(request: Request, connection_id: str):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            svc.delete(principal, connection_id)
        except ConnectionRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return {"status": "ok"}

    @app.post("/api/connections/{connection_id}/test")
    async def api_test_connection(request: Request, connection_id: str):
        principal = need_reader(request)
        if isinstance(principal, JSONResponse):
            return principal
        preferred = None
        try:
            raw = await request.body()
            if raw:
                body = json.loads(raw.decode("utf-8"))
                if isinstance(body, dict) and body.get("preferred_host_id"):
                    preferred = str(body["preferred_host_id"])
            return svc.test(principal, connection_id, preferred)
        except ConnectionRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except json.JSONDecodeError:
            return json_error(400, "invalid_json")
