"""Rotas /api/ai-settings: agenda do radar e motor/modelo por uso. Ler: editor ou owner. Mudar: owner."""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..ai_settings import AiSettings, SettingsError
from ..errors import AuthorizationError


def register_ai_settings_routes(app: FastAPI, settings: AiSettings, *, json_error, need_editor_or_owner, need_owner):
    @app.get("/api/ai-settings")
    def api_ai_settings(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return settings.view(principal)
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.post("/api/ai-settings")
    async def api_update_ai_settings(request: Request):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = await request.json()
            return settings.update(principal, body)
        except SettingsError as exc:
            return json_error(400, exc.code, hint=exc.hint or None)
        except AuthorizationError:
            return json_error(403, "forbidden")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
