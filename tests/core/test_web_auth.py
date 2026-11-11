"""Login web por device flow (fakes, sem rede). Extra [web]."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub
from forge_core.auth.store import AuthStore
from forge_core.config import load_settings
from forge_core.storage import open_repository
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, require_editor
from forge_core.errors import AuthorizationError

HOST = {"Host": "127.0.0.1:8091"}


class Scripted(FakeGitHub):
    def __init__(self, replies=None, token="gho_SENTINELA_webxxxxxxxxxxxxxxxxxxxx", user=(42, "maria")):
        super().__init__()
        self._replies = list(replies or [])
        self._token = token
        self._user = user

    def post_form(self, url, data):
        if url.endswith("/device/code"):
            return {
                "device_code": "dc-web",
                "user_code": "ABCD-1234",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 1,
            }
        if self._replies:
            item = self._replies.pop(0)
            return item if isinstance(item, dict) else {"error": item}
        return {"access_token": self._token}

    def get_json(self, url, token):
        return {"id": self._user[0], "login": self._user[1]}


def _settings(tmp_path):
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
    })


def _client(tmp_path, gh, repo=None):
    settings = _settings(tmp_path)
    repo = repo or open_repository(settings.database_url)
    app = create_app(repo, settings, transport=gh)
    return TestClient(app, base_url="http://127.0.0.1:8091"), repo


def _csrf(client):
    r = client.get("/api/health", headers=HOST)
    assert r.status_code == 200
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return token


def test_happy_path_device_flow_sets_httponly_session_and_whoami(tmp_path):
    client, repo = _client(tmp_path, Scripted())
    csrf = _csrf(client)
    start = client.post(
        "/api/auth/login/start",
        headers={**HOST, CSRF_HEADER: csrf},
    )
    assert start.status_code == 200
    body = start.json()
    assert body["user_code"] == "ABCD-1234"
    assert body["verification_uri"] == "https://github.com/login/device"
    status = client.get("/api/auth/login/status", headers=HOST)
    assert status.json()["status"] == "authorized"
    session = status.cookies.get(SESSION_COOKIE)
    assert session
    set_cookie = status.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie
    who = client.get("/api/auth/whoami", headers=HOST)
    assert who.status_code == 200
    data = who.json()
    assert data["login"] == "maria"
    assert data["identity"] == "gh:42"
    assert "roles" in data
    dump = repr(repo.fetch("SELECT * FROM sessions"))
    assert "gho_SENTINELA" not in dump
    assert "dc-web" not in dump


def test_denied_and_expired_device_flow(tmp_path):
    client, _repo = _client(tmp_path, Scripted(["access_denied"]))
    csrf = _csrf(client)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    denied = client.get("/api/auth/login/status", headers=HOST)
    assert denied.json()["status"] == "denied"
    assert not denied.cookies.get(SESSION_COOKIE)

    now = [0.0]
    settings = _settings(tmp_path)
    repo = open_repository(f"sqlite:///{tmp_path / 'e.db'}")
    app = create_app(repo, settings, transport=Scripted(["authorization_pending"] * 20), monotonic=lambda: now[0])
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    csrf = _csrf(client)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    now[0] = 1000.0
    expired = client.get("/api/auth/login/status", headers=HOST)
    assert expired.json()["status"] == "expired"


def test_host_allowlist_rejects_other_hosts(tmp_path):
    client, _repo = _client(tmp_path, Scripted())
    r = client.get("/api/health", headers={"Host": "evil.example:8091"})
    assert r.status_code == 400
    assert r.json()["error"] == "host_rejected"


def test_csrf_rejection_on_post(tmp_path):
    client, _repo = _client(tmp_path, Scripted())
    _csrf(client)
    r = client.post("/api/auth/login/start", headers=HOST)
    assert r.status_code == 403
    assert r.json()["error"] == "csrf"


def test_first_request_csrf_token_matches_set_cookie_and_post_passes(tmp_path):
    client, _repo = _client(tmp_path, Scripted())
    r = client.get("/api/health", headers=HOST)
    cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else [r.headers.get("set-cookie")]
    csrf_headers = [c for c in cookies if c and "forge_csrf=" in c.lower()]
    tokens = set()
    for header in csrf_headers:
        piece = [p for p in header.split(";") if p.strip().lower().startswith("forge_csrf=")][0]
        tokens.add(piece.split("=", 1)[1].strip())
    assert len(tokens) == 1
    token = tokens.pop()
    assert client.cookies.get(CSRF_COOKIE) == token
    start = client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: token})
    assert start.status_code == 200
    assert start.json()["user_code"] == "ABCD-1234"


def test_effective_host_trusts_only_listed_proxy(monkeypatch):
    from forge_core.web.security import effective_host, peer_is_trusted

    assert effective_host(
        "backend:8091", "127.0.0.1:8090", "172.18.0.5",
        trust_forwarded=True, trusted_proxies=("172.18.0.5",),
    ) == "127.0.0.1:8090"
    assert effective_host(
        "backend:8091", "evil.example", "1.2.3.4",
        trust_forwarded=True, trusted_proxies=("172.18.0.5",),
    ) == "backend:8091"
    monkeypatch.setattr(
        "forge_core.web.security.socket.getaddrinfo",
        lambda host, *a, **k: [(0, 0, 0, "", ("172.18.0.9", 0))],
    )
    assert peer_is_trusted("172.18.0.9", ("forge_frontend",))
    assert effective_host(
        "backend:8091", "127.0.0.1:8090", "172.18.0.9",
        trust_forwarded=True, trusted_proxies=("forge_frontend",),
    ) == "127.0.0.1:8090"


def test_cookie_not_secure_by_default_and_no_cors(tmp_path):
    client, _repo = _client(tmp_path, Scripted())
    r = client.get("/api/health", headers={**HOST, "Origin": "https://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
    assert "secure" not in r.headers.get("set-cookie", "").lower().split("forge_csrf")[-1]
    assert r.headers.get("content-security-policy") == "default-src 'self'"
    assert r.headers.get("x-frame-options") == "DENY"


def test_logout_revokes_and_owner_is_not_editor(tmp_path):
    client, repo = _client(tmp_path, Scripted())
    csrf = _csrf(client)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    client.get("/api/auth/login/status", headers=HOST)
    who = client.get("/api/auth/whoami", headers=HOST).json()
    store = AuthStore(repo)
    principal = store.resolve_session(client.cookies.get(SESSION_COOKIE))
    with pytest.raises(AuthorizationError, match="forbidden"):
        require_editor(store, principal)
    csrf = client.cookies.get(CSRF_COOKIE) or _csrf(client)
    out = client.post("/api/auth/logout", headers={**HOST, CSRF_HEADER: csrf})
    assert out.status_code == 200
    set_cookie = "\n".join(
        out.headers.get_list("set-cookie") if hasattr(out.headers, "get_list") else [out.headers.get("set-cookie", "")]
    ).lower()
    session_bits = [line for line in set_cookie.split("\n") if "forge_session=" in line]
    assert session_bits
    blob = session_bits[0]
    assert "path=/" in blob
    assert "samesite=strict" in blob
    assert "httponly" in blob
    assert client.get("/api/auth/whoami", headers=HOST).status_code == 401
    actions = [a.action for a in repo.list_audit()]
    assert "auth.web_login_ok" in actions
    assert "auth.web_logout" in actions
