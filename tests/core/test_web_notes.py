"""API /api/notes: CSRF, papéis, corpo fora do audit_log."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap
from forge_core.auth.store import AuthStore
from forge_core.config import load_settings
from forge_core.storage import open_repository
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

HOST = {"Host": "127.0.0.1:8091"}
SENTINEL = "SENTINELA_WEB_NOTA_xyz<script>alert(1)</script>"
ISSUE = "ferreiraeborzone/site#9"


class Scripted(FakeGitHub):
    def __init__(self, user=(1000, "dona")):
        super().__init__()
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
        return {"access_token": f"gho_SENTINELA_{self._user[0]}"}

    def get_json(self, url, token):
        return {"id": self._user[0], "login": self._user[1]}


def _settings(tmp_path):
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
        "FORGE_GRAPH_DIR": str(tmp_path / "graphs"),
    })


def _app(tmp_path, *, user=(1000, "dona"), editor=True):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    store = AuthStore(repo)
    if editor:
        store.grant_role(owner, 1000, "editor")
    if user != (1000, "dona"):
        from auth_helpers import person
        person(repo, owner, FakeGitHub(), user[1], user[0], "editor")
    app = create_app(repo, settings, transport=Scripted(user=user))
    return TestClient(app, base_url="http://127.0.0.1:8091"), repo


def _csrf(client):
    r = client.get("/api/health", headers=HOST)
    assert r.status_code == 200
    return client.cookies.get(CSRF_COOKIE)


def _login(client):
    csrf = _csrf(client)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    status = client.get("/api/auth/login/status", headers=HOST)
    assert status.json()["status"] == "authorized"
    assert client.cookies.get(SESSION_COOKIE)
    return client.cookies.get(CSRF_COOKIE) or csrf


def _h(csrf):
    return {**HOST, CSRF_HEADER: csrf, "Content-Type": "application/json"}


def test_csrf_blocks_note_create(tmp_path):
    client, _repo = _app(tmp_path)
    _login(client)
    r = client.post("/api/notes", headers=HOST, json={"issue_key": ISSUE, "title": "a", "body": "b"})
    assert r.status_code == 403
    assert r.json()["error"] == "csrf"


def test_editor_crud_note_without_logging_body(tmp_path):
    client, repo = _app(tmp_path)
    csrf = _login(client)
    created = client.post(
        "/api/notes", headers=_h(csrf),
        json={"issue_key": ISSUE, "title": "Pista", "body": SENTINEL},
    )
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["body"] == SENTINEL
    note_id = data["id"]
    listed = client.get("/api/notes", headers=HOST, params={"issue": ISSUE})
    assert listed.status_code == 200
    assert listed.json()["notes"][0]["id"] == note_id
    assert "body" not in listed.json()["notes"][0]
    got = client.get(f"/api/notes/{note_id}", headers=HOST)
    assert got.json()["body"] == SENTINEL
    updated = client.post(
        f"/api/notes/{note_id}", headers=_h(csrf),
        json={"title": "Pista 2", "body": SENTINEL},
    )
    assert updated.status_code == 200
    deleted = client.post(f"/api/notes/{note_id}/delete", headers=_h(csrf), json={})
    assert deleted.status_code == 200
    dump = repr(repo.list_audit())
    assert SENTINEL not in dump
    assert "<script>" not in dump
    assert "gho_SENTINELA" not in dump


def test_unauthenticated_and_solta_forbidden(tmp_path):
    client, _repo = _app(tmp_path)
    r = client.get("/api/notes", headers=HOST)
    assert r.status_code == 401
    from auth_helpers import person
    other = tmp_path / "solta"
    other.mkdir()
    settings = _settings(other)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    person(repo, owner, FakeGitHub(), "solta", 1004)
    app = create_app(repo, settings, transport=Scripted(user=(1004, "solta")))
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    csrf = _login(client)
    denied = client.post(
        "/api/notes", headers=_h(csrf),
        json={"issue_key": ISSUE, "title": "x", "body": "y"},
    )
    assert denied.status_code == 403
    assert SENTINEL not in denied.text
