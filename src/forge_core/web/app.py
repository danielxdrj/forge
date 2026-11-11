"""API JSON FastAPI + páginas mínimas de login (ADR-017). Sem tela de tarefas."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..auth.github import DeviceFlow, DeviceFlowError, Transport, UrllibTransport
from ..auth.store import AuthStore, Principal
from ..config import Settings
from ..errors import AuthenticationError, AuthorizationError
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

_TEMPLATES = Path(__file__).parent / "templates"


def create_app(
    repo: SqlRepository,
    settings: Settings,
    *,
    transport: Transport | None = None,
    monotonic: Callable[[], float] | None = None,
    wall: Callable[[], str] | None = None,
) -> FastAPI:
    if not settings.github_client_id:
        raise ValueError("FORGE_GITHUB_CLIENT_ID é obrigatória para o painel web")
    clock_mono = monotonic or time.monotonic
    clock_wall = wall or (lambda: datetime.now(timezone.utc).isoformat())
    flow = DeviceFlow(settings.github_client_id, transport or UrllibTransport(), clock=clock_mono)
    store = AuthStore(repo, verify=flow.identity, clock=clock_wall)
    pending = PendingStore(clock_mono)
    jinja = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=select_autoescape(["html"]))
    app = FastAPI(title="Forge", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.repo = repo
    app.state.store = store
    app.state.settings = settings
    app.state.require_editor = require_editor

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

    def _ensure_csrf(request: Request, response: Response) -> str:
        token = request.cookies.get(CSRF_COOKIE) or new_token()
        _set_csrf(response, token)
        return token

    def _check_csrf(request: Request, form_token: str | None = None) -> bool:
        submitted = request.headers.get(CSRF_HEADER) or form_token
        return csrf_ok(request.cookies.get(CSRF_COOKIE), submitted)

    def _principal(request: Request) -> Principal | None:
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            return None
        try:
            return store.resolve_session(raw)
        except AuthenticationError:
            return None

    def _json_error(status: int, code: str) -> JSONResponse:
        resp = JSONResponse({"error": code}, status_code=status)
        for key, value in SECURITY_HEADERS.items():
            resp.headers[key] = value
        return resp

    def _html(name: str, *, status: int = 200, **ctx) -> HTMLResponse:
        body = jinja.get_template(name).render(**ctx)
        resp = HTMLResponse(body, status_code=status)
        for key, value in SECURITY_HEADERS.items():
            resp.headers[key] = value
        return resp

    def _apply_session_cookie(response: Response, session_token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE, session_token, max_age=settings.session_ttl_seconds, **_cookie_kw(httponly=True)
        )

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
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(DEVICE_COOKIE, path="/")

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
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if "access-control-allow-origin" in response.headers:
            del response.headers["access-control-allow-origin"]
        csrf = request.cookies.get(CSRF_COOKIE) or new_token()
        _set_csrf(response, csrf)
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/login/start")
    def api_login_start(request: Request):
        if not _check_csrf(request):
            _audit("anon:web", "auth.web_login_fail", "web", "error: csrf")
            return _json_error(403, "csrf")
        try:
            body, browser_id, expires_in = _start_device()
        except DeviceFlowError as exc:
            _audit("anon:web", "auth.web_login_fail", "web", f"error: {exc.code}")
            return _json_error(400, exc.code)
        response = JSONResponse(body)
        response.set_cookie(DEVICE_COOKIE, browser_id, max_age=expires_in, **_cookie_kw(httponly=True))
        _ensure_csrf(request, response)
        return response

    @app.get("/api/auth/login/status")
    def api_login_status(request: Request):
        body, session_token = _poll_device(request.cookies.get(DEVICE_COOKIE))
        response = JSONResponse(body)
        if session_token:
            _apply_session_cookie(response, session_token)
            response.delete_cookie(DEVICE_COOKIE, path="/")
        _ensure_csrf(request, response)
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
        if not _check_csrf(request):
            _audit("anon:web", "auth.web_logout", "web", "error: csrf")
            return _json_error(403, "csrf")
        response = JSONResponse({"status": "ok"})
        _do_logout(request, response)
        _ensure_csrf(request, response)
        return response

    @app.get("/", response_class=HTMLResponse)
    def root(request: Request):
        if _principal(request) is not None:
            return RedirectResponse("/whoami", status_code=303)
        return RedirectResponse("/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_get(request: Request):
        if _principal(request) is not None:
            return RedirectResponse("/whoami", status_code=303)
        body, session_token = _poll_device(request.cookies.get(DEVICE_COOKIE))
        if session_token:
            redir = RedirectResponse("/whoami", status_code=303)
            _apply_session_cookie(redir, session_token)
            redir.delete_cookie(DEVICE_COOKIE, path="/")
            _ensure_csrf(request, redir)
            return redir
        csrf_holder = Response()
        csrf = _ensure_csrf(request, csrf_holder)
        if body.get("status") == "pending":
            page = _html(
                "login.html",
                csrf_token=csrf,
                pending=True,
                user_code=body["user_code"],
                verification_uri=body["verification_uri"],
                error=None,
            )
        else:
            error = None if body.get("status") in (None, "idle") else body.get("status")
            page = _html("login.html", csrf_token=csrf, pending=False, error=error)
        _copy_cookies(csrf_holder, page)
        return page

    @app.post("/login")
    async def login_post(request: Request, csrf_token: str = Form(default="")):
        if not _check_csrf(request, csrf_token):
            _audit("anon:web", "auth.web_login_fail", "web", "error: csrf")
            return _html("login.html", status=403, csrf_token=csrf_token, pending=False, error="csrf")
        try:
            _body, browser_id, expires_in = _start_device()
        except DeviceFlowError as exc:
            _audit("anon:web", "auth.web_login_fail", "web", f"error: {exc.code}")
            page = _html("login.html", csrf_token=csrf_token, pending=False, error=exc.code)
            _ensure_csrf(request, page)
            return page
        response = RedirectResponse("/login", status_code=303)
        response.set_cookie(DEVICE_COOKIE, browser_id, max_age=expires_in, **_cookie_kw(httponly=True))
        _ensure_csrf(request, response)
        return response

    @app.get("/whoami", response_class=HTMLResponse)
    def whoami_get(request: Request):
        principal = _principal(request)
        if principal is None:
            return RedirectResponse("/login", status_code=303)
        holder = Response()
        csrf = _ensure_csrf(request, holder)
        page = _html(
            "whoami.html",
            csrf_token=csrf,
            login=principal.login,
            identity=principal.identity_id,
            roles=roles_of(store, principal.identity_id),
        )
        _copy_cookies(holder, page)
        return page

    @app.post("/logout")
    async def logout_post(request: Request, csrf_token: str = Form(default="")):
        if not _check_csrf(request, csrf_token):
            _audit("anon:web", "auth.web_logout", "web", "error: csrf")
            return _json_error(403, "csrf")
        response = RedirectResponse("/login", status_code=303)
        _do_logout(request, response)
        _ensure_csrf(request, response)
        return response

    return app


def _copy_cookies(src: Response, dest: Response) -> None:
    for header in src.raw_headers:
        if header[0].decode().lower() == "set-cookie":
            dest.raw_headers.append(header)
