"""API /api/investigations: rotas, papéis, redação de segredo e to-task."""
from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap, person
from fastapi.testclient import TestClient

from forge_core.agents.provider import ProviderResponse
from forge_core.config import load_settings
from forge_core.storage import open_repository
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER

HOST = {"Host": "127.0.0.1:8090"}
REPO = "ferreiraeborzone/site"
SECRET_SENTINEL = "SEGREDO_NAO_VAZAR_api_key_xyz"


class Scripted(FakeGitHub):
    def __init__(self, user=(42, "maria")):
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


class FakeAdapter:
    name = "fake-investigation"

    def __init__(self, text="achado qualquer"):
        self.text = text
        self.prompts = []

    def complete(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        return ProviderResponse(text=self.text)


class FakeDraftLLM:
    name = "fake-draft"

    def complete(self, prompt, max_tokens=None):
        return ProviderResponse(text=json.dumps({
            "title": "fix: lentidao no login",
            "solicitado_por": "Ana",
            "objetivo": "Corrigir lentidao.",
            "contexto": "Login lento.",
            "problemas": ["Login demora"],
            "novos_problemas": "",
            "situacao_atual": "Login demora 10s.",
            "comportamento_esperado": ["Login rapido"],
            "criterios": ["Login < 2s"],
            "observacoes": ["nenhuma"],
        }))


def _settings(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
        "FORGE_WEB_HOSTS": "127.0.0.1:8090,localhost:8090,127.0.0.1:8091,localhost:8091",
    })


def _app(tmp_path, *, editor=True, investigation_provider=None, provider=None):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub())
    if editor:
        person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    else:
        person(repo, owner, FakeGitHub(), "maria", 42)
    app = create_app(
        repo, settings, transport=Scripted(),
        investigation_provider=investigation_provider or FakeAdapter(),
        provider=provider, drafts_dir=tmp_path / "drafts",
    )
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


def test_run_list_get_investigation(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    created = client.post(
        "/api/investigations/run", headers=_h(csrf),
        json={"description": "Investigar lentidao no login", "repos": [REPO]},
    )
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["description"] == "Investigar lentidao no login"
    assert data["repos"] == [REPO]
    listed = client.get("/api/investigations", headers=HOST)
    assert listed.status_code == 200
    assert listed.json()["investigations"][0]["id"] == data["id"]
    got = client.get(f"/api/investigations/{data['id']}", headers=HOST)
    assert got.status_code == 200
    assert got.json()["id"] == data["id"]


def test_run_requires_editor_role(tmp_path):
    client, _repo = _app(tmp_path, editor=False)
    csrf = _login(client)
    denied = client.post(
        "/api/investigations/run", headers=_h(csrf),
        json={"description": "x", "repos": [REPO]},
    )
    assert denied.status_code == 403


def test_run_rejects_repo_outside_allowlist(tmp_path):
    client, _repo = _app(tmp_path)
    csrf = _login(client)
    denied = client.post(
        "/api/investigations/run", headers=_h(csrf),
        json={"description": "x", "repos": ["evil/out"]},
    )
    assert denied.status_code == 400
    assert denied.json()["error"] == "repo_not_allowed"


def test_result_never_leaks_secret_over_api(tmp_path):
    adapter = FakeAdapter(text=f"achado: token=ghp_{'A' * 36} e api_key={SECRET_SENTINEL}")
    client, _repo = _app(tmp_path, investigation_provider=adapter)
    csrf = _login(client)
    created = client.post(
        "/api/investigations/run", headers=_h(csrf),
        json={"description": "verificar logs", "repos": [REPO]},
    )
    assert created.status_code == 200
    assert "ghp_" not in created.text
    assert SECRET_SENTINEL not in created.text


def test_to_task_generates_draft_from_investigation(tmp_path):
    client, _repo = _app(tmp_path, provider=FakeDraftLLM())
    csrf = _login(client)
    created = client.post(
        "/api/investigations/run", headers=_h(csrf),
        json={"description": "Investigar lentidao no login", "repos": [REPO]},
    )
    inv_id = created.json()["id"]
    to_task = client.post(
        f"/api/investigations/{inv_id}/to-task", headers=_h(csrf), json={"repo": REPO},
    )
    assert to_task.status_code == 200, to_task.text
    body = to_task.json()
    assert body["repo"] == REPO
    assert "task_id" in body


def test_to_task_without_draft_provider_returns_service_unavailable(tmp_path):
    client, _repo = _app(tmp_path, provider=None)
    csrf = _login(client)
    created = client.post(
        "/api/investigations/run", headers=_h(csrf),
        json={"description": "Investigar lentidao no login", "repos": [REPO]},
    )
    inv_id = created.json()["id"]
    to_task = client.post(
        f"/api/investigations/{inv_id}/to-task", headers=_h(csrf), json={"repo": REPO},
    )
    assert to_task.status_code == 503
