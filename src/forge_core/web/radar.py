"""Rotas /api/radar: radar de prioridades do Backlog de TI. Leitura e disparo: editor ou owner."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError
from ..radar.service import RadarError, RadarService


def register_radar_routes(app: FastAPI, radar: RadarService, *, json_error, need_editor_or_owner):
    def _rule(exc: RadarError) -> JSONResponse:
        status = {"not_found": 404, "busy": 409, "gh_missing": 503}.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/radar")
    def api_radar(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return radar.overview(principal)
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.post("/api/radar/run")
    def api_radar_run(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            body = radar.start_manual(principal)
        except RadarError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return JSONResponse(body, status_code=202)

    @app.get("/api/radar/reports")
    def api_radar_reports(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return {"reports": radar.history(principal)}
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.get("/api/radar/reports/{report_id}")
    def api_radar_report(request: Request, report_id: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return radar.get(principal, report_id)
        except RadarError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
