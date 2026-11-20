"""Rota /api/areas: catálogo somente leitura das áreas e dos agentes planejados."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..areas import catalog


def register_area_routes(app: FastAPI, *, need_editor_or_owner):
    @app.get("/api/areas")
    def api_areas(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        return catalog()
