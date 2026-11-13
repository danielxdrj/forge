"""API /api/agents: catálogo, métricas, aprovação de escrita (owner/editor)."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap, person
from fastapi.testclient import TestClient

from forge_core.config import load_settings
from forge_core.storage import open_repository
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER

HOST = {"Host": "127.0.0.1:8090"}


class Scripted(FakeGitHub):
    def __init__(self, user):
        super().__init__()
        self._user = user

    def post_form(self, url, data):
        if url.endswith("/device/code"):
            return {
                "device_code": "dc-web", "user_code": "ABCD-1234",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900, "interval": 1,
            }
        return {"access_token": f"gho_SENTINELA_{self._user[0]}"}

    def get_json(self, url, token):
        return {"id": self._user[0], "login": self._user[1]}


def _settings(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
        "FORGE_WEB_HOSTS": "127.0.0.1:8090,localhost:8090,127.0.0.1:8091,localhost:8091",
    })


def _app(tmp_path, *, user=(1000, "dona"), role="owner"):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    if user != (1000, "dona"):
        person(repo, owner, FakeGitHub(), user[1], user[0], role)
    app = create_app(repo, settings, transport=Scripted(user=user))
    client = TestClient(app, base_url="http://127.0.0.1:8090")
    return client, repo


def _login(client):
    client.get("/api/health", headers=HOST)
    csrf = client.cookies.get(CSRF_COOKIE)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    status = client.get("/api/auth/login/status", headers=HOST)
    assert status.json()["status"] == "authorized"
    return client.cookies.get(CSRF_COOKIE) or csrf


def _h(csrf):
    return {**HOST, CSRF_HEADER: csrf, "Content-Type": "application/json"}


def test_create_list_get_and_pause_agent(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    created = client.post(
        "/api/agents", headers=_h(csrf),
        json={"name": "bot-deploy", "scope": "development", "description": "x"},
    )
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["status"] == "active"
    listed = client.get("/api/agents", headers=HOST)
    assert listed.status_code == 200
    assert listed.json()["metrics"]["total"] == 1
    got = client.get(f"/api/agents/{data['id']}", headers=HOST)
    assert got.status_code == 200
    assert got.json()["agent"]["id"] == data["id"]
    paused = client.post(
        f"/api/agents/{data['id']}", headers=_h(csrf), json={"status": "paused"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"


def test_create_requires_owner_editor_cannot(tmp_path):
    client, _repo = _app(tmp_path, user=(42, "maria"), role="editor")
    csrf = _login(client)
    denied = client.post(
        "/api/agents", headers=_h(csrf), json={"name": "x", "scope": "development"},
    )
    assert denied.status_code == 403


def test_editor_can_list_but_not_create(tmp_path):
    client, _repo = _app(tmp_path, user=(42, "maria"), role="editor")
    _login(client)
    listed = client.get("/api/agents", headers=HOST)
    assert listed.status_code == 200


def test_write_permission_to_locked_resource_is_rejected(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    r = client.post(
        "/api/agents", headers=_h(csrf),
        json={"name": "x", "scope": "development", "permissions_write": ["ftp"]},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "write_denied_resource"


def test_company_system_write_requires_approval_flow(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    created = client.post(
        "/api/agents", headers=_h(csrf),
        json={"name": "sistema-x", "scope": "company_system", "permissions_write": ["github"]},
    )
    assert created.status_code == 200
    pending = client.get("/api/agents/approvals", headers=HOST)
    assert pending.status_code == 200
    approvals = pending.json()["approvals"]
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending"
    approved = client.post(
        f"/api/agents/approvals/{approvals[0]['id']}/approve", headers=_h(csrf),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_reject_approval(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    client.post(
        "/api/agents", headers=_h(csrf),
        json={"name": "sistema-y", "scope": "company_system", "permissions_write": ["github"]},
    )
    approvals = client.get("/api/agents/approvals", headers=HOST).json()["approvals"]
    rejected = client.post(
        f"/api/agents/approvals/{approvals[0]['id']}/reject", headers=_h(csrf),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_approvals_route_not_shadowed_by_agent_id_route(tmp_path):
    client, _repo = _app(tmp_path)
    _login(client)
    r = client.get("/api/agents/approvals", headers=HOST)
    assert r.status_code == 200
    assert "approvals" in r.json()
