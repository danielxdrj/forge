"""Cabeçalhos, Host allowlist, CSRF double-submit e sessão cookie (ADR-017)."""
from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from ..auth.store import AuthStore, Principal, ROLES
from ..errors import AuthenticationError, AuthorizationError

SESSION_COOKIE = "forge_session"
CSRF_COOKIE = "forge_csrf"
DEVICE_COOKIE = "forge_device"
CSRF_HEADER = "X-CSRF-Token"

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def require_editor(store: AuthStore, principal: Principal) -> Principal:
    """Exige o papel editor. Owner não implica editor (ADR-014 D4 / ADR-016 D4)."""
    return store.require(principal, "editor")


def roles_of(store: AuthStore, identity_id: str) -> list[str]:
    return [role for role in ROLES if store.has_role(identity_id, role)]


def session_expires_at(ttl_seconds: int, now: Callable[[], str] | None = None) -> str:
    if now is not None:
        current = datetime.fromisoformat(now().replace("Z", "+00:00"))
    else:
        current = datetime.now(timezone.utc)
    return (current + timedelta(seconds=ttl_seconds)).isoformat()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(cookie: str | None, submitted: str | None) -> bool:
    if not cookie or not submitted:
        return False
    if len(cookie) > 128 or len(submitted) > 128:
        return False
    return hmac.compare_digest(cookie, submitted)


def host_allowed(host: str, allowlist: tuple[str, ...]) -> bool:
    return host.strip().lower() in {h.lower() for h in allowlist}


def effective_host(host_header: str, forwarded_host: str | None, peer_ip: str | None,
                   *, trust_forwarded: bool, trusted_proxies: tuple[str, ...]) -> str:
    """Host do pedido. X-Forwarded-Host só vale se o peer for um proxy confiável da rede compose."""
    if trust_forwarded and peer_ip and peer_ip in trusted_proxies:
        fwd = (forwarded_host or "").split(",")[0].strip()
        if fwd:
            return fwd
    return host_header or ""
