"""API JSON FastAPI (ADR-017). Sem HTML: a UI está no forge_frontend."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..auth.github import DeviceFlow, DeviceFlowError, Transport, UrllibTransport
from ..auth.store import AuthStore, Principal
from ..config import Settings
from ..errors import AuthenticationError, AuthorizationError, DraftError
from ..logging import redact
from ..storage.sql import SqlRepository
from .pending import PendingLogin, PendingStore
from .security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    DEVICE_COOKIE,
    SECURITY_HEADERS,
    SESSION_COOKIE,
    csrf_ok,
    effective_host,
    host_allowed,
    new_token,
    require_editor,
    roles_of,
    session_expires_at,
)
from .tasks import WebTaskService

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class GenerateIn(BaseModel):
    repo: str
    context: str


class DraftFieldsIn(BaseModel):
    tipo: str = ""
    prioridade: str = ""
    size: str = ""
    body_md: str | None = None


class ConfirmIn(BaseModel):
    preview_hash: str = Field(min_length=1, max_length=128)


def create_app(
    repo: SqlRepository,
    settings: Settings,
    *,
    transport: Transport | None = None,
    monotonic: Callable[[], float] | None = None,
    wall: Callable[[], str] | None = None,
    provider=None,
    gh=None,
    drafts_dir: Path | None = None,
) -> FastAPI:
    if not settings.github_client_id:
        raise ValueError("FORGE_GITHUB_CLIENT_ID é obrigatória para o painel web")
    clock_mono = monotonic or time.monotonic
    clock_wall = wall or (lambda: datetime.now(timezone.utc).isoformat())
    flow = DeviceFlow(settings.github_client_id, transport or UrllibTransport(), clock=clock_mono)
    store = AuthStore(repo, verify=flow.identity, clock=clock_wall)
    pending = PendingStore(clock_mono)
    from ..tasks.service import TaskService

    tasks = TaskService(repo)
    panel = WebTaskService(repo, tasks, provider, gh, drafts_dir=drafts_dir)
    app = FastAPI(title="Forge", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.repo = repo
    app.state.store = store
    app.state.settings = settings
    app.state.require_editor = require_editor
    app.state.panel = panel

    def _audit(actor: str, action: str, target: str, result: str) -> None:
        repo.record_audit(actor, action, target, redact(result))

    def _cookie_kw(*, httponly: bool) -> dict:
        return {
            "httponly": httponly,
            "samesite": "strict",
            "path": "/",
            "secure": settings.cookie_secure,
        }

    def _set_csrf(response: Response, token: str) -> None:
        response.set_cookie(
            CSRF_COOKIE, token, max_age=settings.session_ttl_seconds, **_cookie_kw(httponly=False)
        )

    def _principal(request: Request) -> Principal | None:
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            return None
        try:
            return store.resolve_session(raw)
        except AuthenticationError:
            return None

    def _json_error(status: int, code: str, **extra) -> JSONResponse:
        payload = {"error": code, **{k: v for k, v in extra.items() if v not in (None, "", [])}}
        resp = JSONResponse(payload, status_code=status)
        for key, value in SECURITY_HEADERS.items():
            resp.headers[key] = value
        return resp

    def _draft_error(exc: DraftError) -> JSONResponse:
        code = exc.code
        status = {
            "diff_changed": 409,
            "draft_published": 409,
            "draft_cancelled": 409,
            "draft_missing": 404,
            "task_missing": 404,
            "provider_missing": 503,
            "gh_missing": 503,
            "gh_not_logged": 503,
            "cursor_cli_missing": 503,
            "provider_error": 502,
            "forbidden": 403,
        }.get(code, 400)
        extra = {}
        if exc.fields:
            extra["fields"] = list(exc.fields)
        if exc.hint:
            extra["hint"] = exc.hint
        return _json_error(status, code, **extra)

    def _apply_session_cookie(response: Response, session_token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE, session_token, max_age=settings.session_ttl_seconds, **_cookie_kw(httponly=True)
        )

    def _delete_auth_cookies(response: Response) -> None:
        kw = {
            "path": "/",
            "samesite": "strict",
            "httponly": True,
            "secure": settings.cookie_secure,
        }
        response.delete_cookie(SESSION_COOKIE, **kw)
        response.delete_cookie(DEVICE_COOKIE, **kw)

    def _start_device() -> tuple[dict, str, int]:
        dc = flow.start()
        browser_id = new_token()
        pending.put(
            browser_id,
            PendingLogin(device=dc, started=clock_mono(), last_poll=0.0, interval=float(dc.interval)),
        )
        _audit("anon:web", "auth.web_login_start", "web", "ok")
        body = {
            "status": "pending",
            "user_code": dc.user_code,
            "verification_uri": dc.verification_uri,
            "expires_in": dc.expires_in,
        }
        return body, browser_id, dc.expires_in

    def _poll_device(browser_id: str | None) -> tuple[dict, str | None]:
        """Devolve (corpo JSON, token de sessão ou None). Token GitHub não sai daqui."""
        item = pending.get(browser_id) if browser_id else None
        if item is None:
            return {"status": "idle"}, None
        now = clock_mono()
        if now >= item.started + item.device.expires_in:
            pending.pop(browser_id)
            _audit("anon:web", "auth.web_login_fail", "web", "error: expired")
            return {"status": "expired"}, None
        if item.last_poll and now < item.last_poll + item.interval:
            return {
                "status": "pending",
                "user_code": item.device.user_code,
                "verification_uri": item.device.verification_uri,
            }, None
        item.last_poll = now
        try:
            attempt = flow.poll_once(item.device)
        except DeviceFlowError as exc:
            pending.pop(browser_id)
            _audit("anon:web", "auth.web_login_fail", "web", f"error: {exc.code}")
            return {"status": exc.code}, None
        if attempt.slow_down:
            item.interval += 5.0
        if not attempt.token:
            return {
                "status": "pending",
                "user_code": item.device.user_code,
                "verification_uri": item.device.verification_uri,
            }, None
        github_token = attempt.token
        try:
            expires = session_expires_at(settings.session_ttl_seconds, clock_wall)
            principal, session_token = store.open_session(github_token, expires_at=expires)
        finally:
            github_token = None
            attempt = None
        pending.pop(browser_id)
        _audit(principal.identity_id, "auth.web_login_ok", f"session:{principal.session_id}", "ok")
        return {"status": "authorized", "login": principal.login}, session_token

    def _do_logout(request: Request, response: Response) -> None:
        principal = _principal(request)
        if principal is not None:
            try:
                store.revoke_session(principal)
            except (AuthenticationError, AuthorizationError):
                _audit(principal.identity_id, "auth.web_logout", f"session:{principal.session_id}", "error: invalid")
            else:
                _audit(principal.identity_id, "auth.web_logout", f"session:{principal.session_id}", "ok")
        _delete_auth_cookies(response)

    def _need_principal(request: Request) -> Principal | JSONResponse:
        principal = _principal(request)
        if principal is None:
            return _json_error(401, "invalid_session")
        return principal

    def _need_editor(request: Request) -> Principal | JSONResponse:
        principal = _need_principal(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return require_editor(store, principal)
        except AuthorizationError:
            return _json_error(403, "forbidden")

    @app.middleware("http")
    async def _secure(request: Request, call_next):
        peer = request.client.host if request.client else None
        host = effective_host(
            request.headers.get("host", ""),
            request.headers.get("x-forwarded-host"),
            peer,
            trust_forwarded=settings.trust_forwarded,
            trusted_proxies=settings.trusted_proxies,
        )
        if not host_allowed(host, settings.web_hosts):
            _audit("anon:web", "auth.host_rejected", "web", "error: host")
            return _json_error(400, "host_rejected")
        token = request.cookies.get(CSRF_COOKIE) or new_token()
        request.state.csrf_token = token
        if request.method not in _SAFE_METHODS:
            submitted = request.headers.get(CSRF_HEADER)
            if not csrf_ok(request.cookies.get(CSRF_COOKIE), submitted):
                _audit("anon:web", "auth.csrf", "web", "error: csrf")
                return _json_error(403, "csrf")
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if "access-control-allow-origin" in response.headers:
            del response.headers["access-control-allow-origin"]
        _set_csrf(response, request.state.csrf_token)
        raw_session = request.cookies.get(SESSION_COOKIE)
        if raw_session:
            try:
                principal = store.resolve_session(raw_session)
                store.touch_session(principal, settings.session_ttl_seconds)
                response.set_cookie(
                    SESSION_COOKIE, raw_session, max_age=settings.session_ttl_seconds,
                    **_cookie_kw(httponly=True),
                )
            except AuthenticationError:
                pass
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/login/start")
    def api_login_start(request: Request):
        try:
            body, browser_id, expires_in = _start_device()
        except DeviceFlowError as exc:
            _audit("anon:web", "auth.web_login_fail", "web", f"error: {exc.code}")
            return _json_error(400, exc.code)
        response = JSONResponse(body)
        response.set_cookie(DEVICE_COOKIE, browser_id, max_age=expires_in, **_cookie_kw(httponly=True))
        return response

    @app.get("/api/auth/login/status")
    def api_login_status(request: Request):
        body, session_token = _poll_device(request.cookies.get(DEVICE_COOKIE))
        response = JSONResponse(body)
        if session_token:
            _apply_session_cookie(response, session_token)
            response.delete_cookie(
                DEVICE_COOKIE,
                path="/",
                samesite="strict",
                httponly=True,
                secure=settings.cookie_secure,
            )
        return response

    @app.get("/api/auth/whoami")
    def api_whoami(request: Request):
        principal = _principal(request)
        if principal is None:
            return _json_error(401, "invalid_session")
        return {
            "login": principal.login,
            "identity": principal.identity_id,
            "roles": roles_of(store, principal.identity_id),
        }

    @app.post("/api/auth/logout")
    def api_logout(request: Request):
        response = JSONResponse({"status": "ok"})
        _do_logout(request, response)
        return response

    @app.get("/api/repos")
    def api_repos(request: Request):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        return {"repos": panel.list_repos(principal)}

    @app.get("/api/board/fields")
    def api_board_fields(request: Request):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return panel.board_fields(principal)
        except DraftError as exc:
            return _draft_error(exc)

    @app.post("/api/tasks/generate")
    def api_generate(request: Request, body: GenerateIn):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return panel.generate(principal, body.repo, body.context)
        except DraftError as exc:
            return _draft_error(exc)

    @app.post("/api/tasks/{task_id}/draft")
    def api_update_draft(request: Request, task_id: str, body: DraftFieldsIn):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return panel.update_fields(
                principal, task_id, body.tipo, body.prioridade, body.size, body_md=body.body_md,
            )
        except DraftError as exc:
            return _draft_error(exc)

    @app.post("/api/tasks/{task_id}/confirm")
    def api_confirm(request: Request, task_id: str, body: ConfirmIn):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return panel.confirm(principal, task_id, body.preview_hash)
        except DraftError as exc:
            return _draft_error(exc)

    @app.post("/api/tasks/{task_id}/discard")
    def api_discard(request: Request, task_id: str):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return panel.discard(principal, task_id)
        except DraftError as exc:
            return _draft_error(exc)

    @app.get("/api/tasks")
    def api_list_tasks(request: Request):
        principal = _need_editor(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return panel.list_tasks(principal)
        except DraftError as exc:
            return _draft_error(exc)

    return app
