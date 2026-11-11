"""API de tarefas do painel (fakes de Cursor e gh; sem rede, sem issue real)."""
from __future__ import annotations

import json
import subprocess

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap, person
from forge_core.agents.provider import ProviderResponse
from forge_core.draft.github_gh import GhCli
from forge_core.storage import open_repository
from forge_core.storage.drafts import list_task_links
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from forge_core.config import load_settings

HOST = {"Host": "127.0.0.1:8090"}
REPO = "ferreiraeborzone/site"
TITLE = "fix: login recusa senha valida"
ISSUE_URL = "https://github.com/ferreiraeborzone/site/issues/9"
CONTEXT = "O login recusa senha valida na tela de autenticacao."
VALID = {
    "title": TITLE,
    "solicitado_por": "Ana",
    "objetivo": "Corrigir o login.",
    "contexto": "Tela de autenticacao.",
    "problemas": ["Senha valida e recusada"],
    "novos_problemas": "",
    "situacao_atual": "O botao entra e volta erro.",
    "comportamento_esperado": ["Aceitar senha valida"],
    "criterios": ["Teste de login passa"],
    "observacoes": ["So o modulo de login"],
}
GRAPHQL_FIELDS = {
    "data": {
        "node": {
            "fields": {
                "nodes": [
                    {
                        "id": "f-s", "name": "Sprint",
                        "configuration": {
                            "iterations": [
                                {"id": "it-now", "title": "Semana 45",
                                 "startDate": "2026-11-03", "duration": 21},
                            ],
                            "completedIterations": [],
                        },
                    },
                    {"id": "f-t", "name": "Tipo", "options": [{"id": "o-bug", "name": "Bug"}]},
                    {"id": "f-p", "name": "Prioridade", "options": [{"id": "o-high", "name": "Alta"}]},
                    {"id": "f-z", "name": "Size", "options": [{"id": "o-3", "name": "3"}]},
                ]
            }
        }
    }
}
META_OK = {"tipo": "Bug", "prioridade": "Alta", "size": "3"}


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


class FakeLLM:
    name = "fake"

    def __init__(self, text=None):
        self.text = text if text is not None else json.dumps(VALID)
        self.prompts = []

    def complete(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        return ProviderResponse(text=self.text)


def _gh_script(opts=None):
    opts = opts or {}
    created = opts.setdefault("created", {"n": 0})

    def runner(argv, **kwargs):
        cmd = argv[1:]
        stdout = ""
        if cmd[:2] == ["auth", "status"]:
            stdout = "Logged in to github.com as danielxdrj\nToken scopes: 'repo', 'project'\n"
        elif cmd[:2] == ["project", "view"]:
            stdout = json.dumps({"id": "PVT_proj", "title": "IT Backlog", "number": 13})
        elif cmd[:2] == ["api", "graphql"]:
            blob = " ".join(cmd)
            if "ProjectV2Item" in blob:
                stdout = json.dumps({"data": {"node": {"fieldValues": {"nodes": [
                    {"name": "Bug", "field": {"id": "f-t", "name": "Tipo"}},
                    {"name": "3", "field": {"id": "f-z", "name": "Size"}},
                    {"title": "Semana 45", "field": {"id": "f-s", "name": "Sprint"}},
                    {"name": "Alta", "field": {"id": "f-p", "name": "Prioridade"}},
                ]}}}})
            else:
                stdout = json.dumps(GRAPHQL_FIELDS)
        elif cmd[:2] == ["issue", "create"]:
            created["n"] += 1
            stdout = ISSUE_URL + "\n"
        elif cmd[:2] == ["issue", "view"]:
            stdout = json.dumps({"number": 9, "url": ISSUE_URL, "title": TITLE, "state": "OPEN"})
        elif cmd[:2] == ["project", "item-add"]:
            if opts.get("fail_add") and created["n"] <= opts.get("fail_until", 1):
                return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"fail add")
            stdout = json.dumps({"id": "PVTI_item"})
        elif cmd[:2] == ["project", "item-edit"]:
            stdout = "{}"
        elif cmd[:2] == ["issue", "develop"] and "--list" in cmd:
            stdout = ""
        elif cmd[:2] == ["issue", "develop"]:
            stdout = "https://github.com/ferreiraeborzone/site/tree/9-login-recusa-senha-valida"
        elif cmd[:2] == ["pr", "list"]:
            stdout = opts.get("pr_list", "[]")
        else:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
        return subprocess.CompletedProcess(argv, 0, stdout=stdout.encode(), stderr=b"")
    return runner


def _settings(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}",
        "FORGE_WEB_HOSTS": "127.0.0.1:8090,localhost:8090,127.0.0.1:8091,localhost:8091",
    })


def _app(tmp_path, *, editor=True, gh_opts=None, provider=None):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub())
    if editor:
        person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    else:
        person(repo, owner, FakeGitHub(), "maria", 42)
    runner = _gh_script(gh_opts)
    from datetime import date
    gh = GhCli(runner=runner, today=date(2026, 11, 8))
    app = create_app(
        repo, settings, transport=Scripted(),
        provider=provider or FakeLLM(), gh=gh, drafts_dir=tmp_path / "drafts",
    )
    client = TestClient(app, base_url="http://127.0.0.1:8090")
    return client, repo, runner


def _csrf(client):
    r = client.get("/api/health", headers=HOST)
    assert r.status_code == 200
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return token


def _login(client):
    csrf = _csrf(client)
    start = client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    assert start.status_code == 200
    status = client.get("/api/auth/login/status", headers=HOST)
    assert status.json()["status"] == "authorized"
    assert client.cookies.get(SESSION_COOKIE)
    return client.cookies.get(CSRF_COOKIE) or csrf


def _h(csrf):
    return {**HOST, CSRF_HEADER: csrf, "Content-Type": "application/json"}


def test_repos_allowlist_and_reject_unknown(tmp_path):
    client, _repo, _ = _app(tmp_path)
    csrf = _login(client)
    repos = client.get("/api/repos", headers=HOST)
    assert repos.status_code == 200
    names = {r["full_name"] for r in repos.json()["repos"]}
    assert REPO in names
    assert all(n.startswith("ferreiraeborzone/") for n in names)
    bad = client.post(
        "/api/tasks/generate", headers=_h(csrf),
        json={"repo": "evil/not-allowed", "context": CONTEXT},
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "repo_not_allowed"


def test_context_size_limit(tmp_path):
    client, _repo, _ = _app(tmp_path)
    csrf = _login(client)
    huge = "x" * (64 * 1024 + 1)
    r = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": huge})
    assert r.status_code == 400
    assert r.json()["error"] == "context_too_large"


def test_generate_stores_draft_and_fields_and_confirm_publish(tmp_path):
    created = {"n": 0}
    client, repo, _ = _app(tmp_path, gh_opts={"created": created})
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    assert gen.status_code == 200
    body = gen.json()
    assert body["repo"] == REPO
    assert body["preview_hash"]
    assert "=== ISSUE ===" in body["preview"]
    task_id = body["task_id"]
    rows = repo.fetch("SELECT status, repo FROM drafts WHERE task_id = ?", (task_id,))
    assert rows and rows[0][0] == "rascunho" and rows[0][1] == REPO

    empty = client.post(
        f"/api/tasks/{task_id}/draft", headers=_h(csrf),
        json={"tipo": "", "prioridade": "Alta", "size": "3"},
    )
    assert empty.status_code == 400
    assert empty.json()["error"] == "pending_required"

    pending_marker = client.post(
        f"/api/tasks/{task_id}/draft", headers=_h(csrf),
        json={"tipo": "[PENDENTE]", "prioridade": "Alta", "size": "3"},
    )
    assert pending_marker.status_code == 400

    fields = client.post(f"/api/tasks/{task_id}/draft", headers=_h(csrf), json=META_OK)
    assert fields.status_code == 200
    new_hash = fields.json()["preview_hash"]
    assert new_hash != body["preview_hash"]

    mismatch = client.post(
        f"/api/tasks/{task_id}/confirm", headers=_h(csrf),
        json={"preview_hash": body["preview_hash"]},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"] == "diff_changed"

    ok = client.post(f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": new_hash})
    assert ok.status_code == 200
    data = ok.json()
    assert data["issue_url"] == ISSUE_URL
    assert data["status"] == "publicado"
    kinds = {link.kind for link in list_task_links(repo, task_id)}
    assert "issue" in kinds
    assert "branch" in kinds
    assert created["n"] == 1

    again = client.post(f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": new_hash})
    assert again.status_code == 200
    assert again.json()["issue_url"] == ISSUE_URL
    assert created["n"] == 1

    listed = client.get("/api/tasks", headers=HOST)
    assert listed.status_code == 200
    item = next(t for t in listed.json()["tasks"] if t["id"] == task_id)
    assert item["repo"] == REPO
    assert item["issue_url"] == ISSUE_URL
    assert item["title"] == TITLE


def test_confirm_is_idempotent_after_midway_failure(tmp_path):
    created = {"n": 0}
    opts = {"created": created, "fail_add": True, "fail_until": 1}
    client, repo, _ = _app(tmp_path, gh_opts=opts)
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    task_id = gen.json()["task_id"]
    fields = client.post(f"/api/tasks/{task_id}/draft", headers=_h(csrf), json=META_OK)
    digest = fields.json()["preview_hash"]
    first = client.post(f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": digest})
    assert first.status_code == 400
    assert created["n"] == 1
    opts["fail_add"] = False
    second = client.post(f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": digest})
    assert second.status_code == 200
    assert second.json()["issue_url"] == ISSUE_URL
    assert created["n"] == 1
    kinds = {link.kind for link in list_task_links(repo, task_id)}
    assert kinds >= {"issue", "branch"}


def test_editor_and_csrf_required(tmp_path):
    client, _repo, _ = _app(tmp_path, editor=False)
    csrf = _login(client)
    forbidden = client.post(
        "/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "forbidden"

    client2, _repo2, _ = _app(tmp_path / "b")
    _csrf(client2)
    no_csrf = client2.post("/api/tasks/generate", headers=HOST, json={"repo": REPO, "context": CONTEXT})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"] == "csrf"


def test_board_fields_from_fake_gh(tmp_path):
    client, _repo, _ = _app(tmp_path)
    _login(client)
    r = client.get("/api/board/fields", headers=HOST)
    assert r.status_code == 200
    data = r.json()
    assert "Bug" in data["tipo"]
    assert "Alta" in data["prioridade"]
    assert "3" in data["size"]


def test_list_optionally_stores_pr_from_gh(tmp_path):
    pr_url = "https://github.com/ferreiraeborzone/site/pull/4"
    created = {"n": 0}
    client, repo, _ = _app(tmp_path, gh_opts={
        "created": created,
        "pr_list": json.dumps([{"url": pr_url, "number": 4}]),
    })
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    task_id = gen.json()["task_id"]
    fields = client.post(f"/api/tasks/{task_id}/draft", headers=_h(csrf), json=META_OK)
    client.post(f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": fields.json()["preview_hash"]})
    listed = client.get("/api/tasks", headers=HOST)
    item = next(t for t in listed.json()["tasks"] if t["id"] == task_id)
    assert item["pr_url"] == pr_url
    kinds = {link.kind for link in list_task_links(repo, task_id)}
    assert "pr" in kinds


def test_html_login_routes_are_gone(tmp_path):
    client, _repo, _ = _app(tmp_path)
    _csrf(client)
    assert client.get("/login", headers=HOST).status_code == 404
    assert client.get("/whoami", headers=HOST).status_code == 404
    assert client.get("/", headers=HOST).status_code == 404
