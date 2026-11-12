"""API /api/connections: papéis, CSRF, cofre desligado e segredo fora do JSON."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
cryptography = pytest.importorskip("cryptography")
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap
from forge_core.auth.store import AuthStore
from forge_core.connections.probes import ProbeError
from forge_core.connections.vault import ConnectionsVault
from forge_core.config import load_settings
from forge_core.storage import open_repository
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

HOST = {"Host": "127.0.0.1:8091"}
SECRET = "token-ou-senha-ficticia"


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


class FakeProbes:
    def __init__(self):
        self.calls = []

    def test_one(self, conn_type, host, port, username, secret, database, remote_path):
        self.calls.append(host)
        if host == "falha.example.invalid":
            raise ProbeError("timeout")


def _settings(tmp_path):
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
    })


def _vault(tmp_path):
    path = tmp_path / "forge_connections_key"
    path.write_bytes(Fernet.generate_key())
    return ConnectionsVault.from_key_file(str(path))


def _app(tmp_path, *, user=(1000, "dona"), editor=True, vault=None, probes=None):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    store = AuthStore(repo)
    if editor:
        store.grant_role(owner, 1000, "editor")
    if user != (1000, "dona"):
        from auth_helpers import person
        person(repo, owner, FakeGitHub(), user[1], user[0], "editor")
    app = create_app(
        repo, settings, transport=Scripted(user=user),
        vault=vault if vault is not None else _vault(tmp_path),
        probes=probes or FakeProbes(),
    )
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


def _body():
    return {
        "name": "portainer-lab",
        "type": "portainer",
        "user": "admin",
        "port": 9000,
        "secret": SECRET,
        "hosts": [
            {"label": "tailscale", "host": "100.64.0.8", "order": 0},
            {"label": "empresa", "host": "falha.example.invalid", "order": 1},
        ],
        "preferred_index": 0,
    }


def test_csrf_blocks_create(tmp_path):
    client, _repo = _app(tmp_path)
    _login(client)
    r = client.post("/api/connections", headers=HOST, json=_body())
    assert r.status_code == 403
    assert r.json()["error"] == "csrf"


def test_owner_creates_lists_tests_without_leaking_secret(tmp_path):
    probes = FakeProbes()
    client, repo = _app(tmp_path, probes=probes)
    csrf = _login(client)
    created = client.post("/api/connections", headers=_h(csrf), json=_body())
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["secret_set"] is True
    assert "secret" not in data
    assert SECRET not in created.text
    listed = client.get("/api/connections", headers=HOST)
    assert listed.status_code == 200
    assert listed.json()["enabled"] is True
    assert listed.json()["connections"][0]["id"] == data["id"]
    assert SECRET not in listed.text
    tested = client.post(
        f"/api/connections/{data['id']}/test", headers=_h(csrf), json={},
    )
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert tested.json()["host"] == "100.64.0.8"
    assert probes.calls == ["100.64.0.8"]
    assert SECRET not in tested.text
    dump = repr(repo.fetch("SELECT * FROM connections")) + repr(repo.list_audit())
    assert SECRET not in dump
    assert "gho_SENTINELA" not in dump


def test_editor_cannot_mutate_but_can_list_and_test(tmp_path):
    from auth_helpers import person

    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    vault = _vault(tmp_path)
    probes = FakeProbes()
    owner_client = TestClient(
        create_app(repo, settings, transport=Scripted(user=(1000, "dona")), vault=vault, probes=probes),
        base_url="http://127.0.0.1:8091",
    )
    csrf = _login(owner_client)
    created = owner_client.post("/api/connections", headers=_h(csrf), json=_body())
    assert created.status_code == 200
    cid = created.json()["id"]
    editor_client = TestClient(
        create_app(repo, settings, transport=Scripted(user=(42, "maria")), vault=vault, probes=probes),
        base_url="http://127.0.0.1:8091",
    )
    csrf_e = _login(editor_client)
    listed = editor_client.get("/api/connections", headers=HOST)
    assert listed.status_code == 200
    assert listed.json()["connections"][0]["id"] == cid
    denied = editor_client.post("/api/connections", headers=_h(csrf_e), json=_body())
    assert denied.status_code == 403
    tested = editor_client.post(f"/api/connections/{cid}/test", headers=_h(csrf_e), json={})
    assert tested.status_code == 200
    deleted = editor_client.post(f"/api/connections/{cid}/delete", headers=_h(csrf_e), json={})
    assert deleted.status_code == 403


def test_vault_disabled_reports_clearly(tmp_path):
    client, _repo = _app(tmp_path, vault=ConnectionsVault.disabled())
    csrf = _login(client)
    listed = client.get("/api/connections", headers=HOST)
    assert listed.status_code == 200
    body = listed.json()
    assert body["enabled"] is False
    assert body["error"] == "vault_disabled"
    assert "chave" in body["message"].lower() or "desligada" in body["message"].lower()
    created = client.post("/api/connections", headers=_h(csrf), json=_body())
    assert created.status_code == 503
    assert created.json()["error"] == "vault_disabled"
    assert SECRET not in created.text
