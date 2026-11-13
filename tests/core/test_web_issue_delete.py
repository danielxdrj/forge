"""API /api/issues/{owner}/{repo}/{number}/delete: owner, confirmação exata, fallback close."""
from __future__ import annotations

import subprocess

import pytest

fastapi = pytest.importorskip("fastapi")
from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap, person
from fastapi.testclient import TestClient

from forge_core.config import load_settings
from forge_core.draft.github_gh import GhCli
from forge_core.storage import open_repository
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER

HOST = {"Host": "127.0.0.1:8090"}
REPO = "ferreiraeborzone/site"
NUMBER = 9


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


def _runner(*, forbidden=False):
    def run(argv, **kwargs):
        cmd = argv[1:]
        if cmd[0] == "api" and cmd[1].startswith("repos/") and cmd[1].endswith(f"/issues/{NUMBER}"):
            return subprocess.CompletedProcess(argv, 0, stdout=b"I_nodeid123\n", stderr=b"")
        if cmd[:2] == ["api", "graphql"] and "deleteIssue" in " ".join(cmd):
            if forbidden:
                return subprocess.CompletedProcess(
                    argv, 1, stdout=b"", stderr=b"HTTP 403: Resource not accessible by integration",
                )
            return subprocess.CompletedProcess(argv, 0, stdout=b"{}", stderr=b"")
        if cmd[:2] == ["issue", "close"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
    return run


def _settings(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
        "FORGE_WEB_HOSTS": "127.0.0.1:8090,localhost:8090,127.0.0.1:8091,localhost:8091",
    })


def _app(tmp_path, *, user=(1000, "dona"), owner_role=True, forbidden=False):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    if user != (1000, "dona"):
        person(repo, owner, FakeGitHub(), user[1], user[0], *( ["owner"] if owner_role else ["editor"]))
    gh = GhCli(runner=_runner(forbidden=forbidden))
    app = create_app(repo, settings, transport=Scripted(user=user), gh=gh)
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


def test_delete_requires_owner_role(tmp_path):
    client, _repo = _app(tmp_path, user=(42, "maria"), owner_role=False)
    csrf = _login(client)
    r = client.post(
        f"/api/issues/ferreiraeborzone/site/{NUMBER}/delete", headers=_h(csrf),
        json={"confirm": f"{REPO}#{NUMBER}"},
    )
    assert r.status_code == 403


def test_delete_requires_exact_confirmation(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    r = client.post(
        f"/api/issues/ferreiraeborzone/site/{NUMBER}/delete", headers=_h(csrf),
        json={"confirm": "errado"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "confirm_mismatch"


def test_delete_succeeds(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    r = client.post(
        f"/api/issues/ferreiraeborzone/site/{NUMBER}/delete", headers=_h(csrf),
        json={"confirm": f"{REPO}#{NUMBER}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "deleted"


def test_delete_forbidden_without_fallback(tmp_path):
    client, _repo = _app(tmp_path, forbidden=True)
    csrf = _login(client)
    r = client.post(
        f"/api/issues/ferreiraeborzone/site/{NUMBER}/delete", headers=_h(csrf),
        json={"confirm": f"{REPO}#{NUMBER}"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "issue_delete_forbidden"


def test_delete_forbidden_with_fallback_close(tmp_path):
    client, _repo = _app(tmp_path, forbidden=True)
    csrf = _login(client)
    r = client.post(
        f"/api/issues/ferreiraeborzone/site/{NUMBER}/delete", headers=_h(csrf),
        json={"confirm": f"{REPO}#{NUMBER}", "fallback": "close"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "closed"
