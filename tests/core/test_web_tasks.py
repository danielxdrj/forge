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
from forge_core.draft.template import PENDING, SUGGESTION_PREFIX
from forge_core.issues.store import upsert
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
    assert empty.status_code == 200
    assert "tipo" in empty.json()["pending"]

    pending_marker = client.post(
        f"/api/tasks/{task_id}/draft", headers=_h(csrf),
        json={"tipo": "[PENDENTE]", "prioridade": "Alta", "size": "3"},
    )
    assert pending_marker.status_code == 200
    assert "tipo" in pending_marker.json()["pending"]

    unknown = client.post(
        f"/api/tasks/{task_id}/draft", headers=_h(csrf),
        json={"tipo": "NaoExiste", "prioridade": "Alta", "size": "3"},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"] == "invalid_board_option"
    assert "tipo" in unknown.json()["fields"]

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


def test_generate_suggests_board_fields_and_confirm_without_extra_draft(tmp_path):
    payload = dict(VALID, tipo="Bug", prioridade="Alta", size="3")
    client, _repo, _ = _app(tmp_path, provider=FakeLLM(json.dumps(payload)))
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    assert gen.status_code == 200
    body = gen.json()
    assert body["tipo"] == "Bug"
    assert body["prioridade"] == "Alta"
    assert body["size"] == "3"
    assert body["pending"] == []
    assert body["body"]
    ok = client.post(
        f"/api/tasks/{body['task_id']}/confirm",
        headers=_h(csrf),
        json={"preview_hash": body["preview_hash"]},
    )
    assert ok.status_code == 200
    assert ok.json()["issue_url"] == ISSUE_URL


def test_short_context_infers_sections_and_confirm_passes(tmp_path):
    payload = dict(
        VALID,
        objetivo="[PENDENTE]",
        comportamento_esperado=["[PENDENTE]"],
        criterios=["[PENDENTE]"],
        tipo="Bug",
        prioridade="Alta",
        size="3",
    )
    client, _repo, _ = _app(tmp_path, provider=FakeLLM(json.dumps(payload)))
    csrf = _login(client)
    gen = client.post(
        "/api/tasks/generate", headers=_h(csrf),
        json={"repo": REPO, "context": "tarefa de teste, solicitado por carlos daniel"},
    )
    assert gen.status_code == 200
    body = gen.json()
    assert PENDING not in "\n".join(body["pending"])
    assert "comportamento_esperado" not in body["pending"]
    assert "criterios" not in body["pending"]
    assert SUGGESTION_PREFIX in body["body"]
    assert PENDING not in body["body"].split("## Comportamento Esperado", 1)[1].split("## ", 1)[0]
    assert PENDING not in body["body"].split("## Critérios de Aceite", 1)[1].split("## ", 1)[0]
    ok = client.post(
        f"/api/tasks/{body['task_id']}/confirm",
        headers=_h(csrf),
        json={"preview_hash": body["preview_hash"]},
    )
    assert ok.status_code == 200
    assert ok.json()["issue_url"] == ISSUE_URL


def test_confirm_pending_objetivo_still_blocks(tmp_path):
    payload = dict(VALID, tipo="Bug", prioridade="Alta", size="3")
    client, _repo, _ = _app(tmp_path, provider=FakeLLM(json.dumps(payload)))
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    task_id = gen.json()["task_id"]
    edited = gen.json()["body"].replace("Corrigir o login.", PENDING)
    saved = client.post(
        f"/api/tasks/{task_id}/draft",
        headers=_h(csrf),
        json={**META_OK, "body_md": edited},
    )
    assert saved.status_code == 200
    assert "objetivo" in saved.json()["pending"]
    refused = client.post(
        f"/api/tasks/{task_id}/confirm",
        headers=_h(csrf),
        json={"preview_hash": saved.json()["preview_hash"]},
    )
    assert refused.status_code == 400
    data = refused.json()
    assert data["error"] == "pending_fields"
    assert "objetivo" in data["fields"]


def test_edit_body_updates_preview_hash_and_old_hash_conflicts(tmp_path):
    client, _repo, _ = _app(tmp_path)
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    task_id = gen.json()["task_id"]
    old_hash = gen.json()["preview_hash"]
    body = gen.json()["body"]
    edited = body.replace("Corrigir o login.", "Corrigir o login na tela de autenticacao.")
    saved = client.post(
        f"/api/tasks/{task_id}/draft",
        headers=_h(csrf),
        json={**META_OK, "body_md": edited},
    )
    assert saved.status_code == 200
    new_hash = saved.json()["preview_hash"]
    assert new_hash != old_hash
    assert "Corrigir o login na tela de autenticacao." in saved.json()["body"]
    mismatch = client.post(
        f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": old_hash},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"] == "diff_changed"
    ok = client.post(
        f"/api/tasks/{task_id}/confirm", headers=_h(csrf), json={"preview_hash": new_hash},
    )
    assert ok.status_code == 200


def test_board_fields_error_includes_hint(tmp_path):
    def runner(argv, **kwargs):
        cmd = argv[1:]
        if cmd[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(
                argv, 0, stdout=b"Logged in to github.com as danielxdrj\nToken scopes: 'repo'\n", stderr=b"",
            )
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")

    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub())
    person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    from datetime import date
    gh = GhCli(runner=runner, today=date(2026, 11, 8))
    app = create_app(repo, settings, transport=Scripted(), provider=FakeLLM(), gh=gh, drafts_dir=tmp_path / "drafts")
    client = TestClient(app, base_url="http://127.0.0.1:8090")
    _login(client)
    r = client.get("/api/board/fields", headers=HOST)
    assert r.status_code == 400
    assert r.json()["error"] == "project_scope"
    assert "project" in (r.json().get("hint") or "")


def test_branch_from_link_without_tree_keeps_url():
    from types import SimpleNamespace
    from forge_core.web.tasks import _branch_from_link

    assert _branch_from_link(None) is None
    assert _branch_from_link(SimpleNamespace(url="https://github.com/org/repo/tree/feat-x")) == "feat-x"
    assert _branch_from_link(SimpleNamespace(url="feat-x")) == "feat-x"


def test_list_splits_published_and_drafts_discard_is_idempotent(tmp_path):
    created = {"n": 0}
    client, repo, _ = _app(tmp_path, gh_opts={"created": created})
    csrf = _login(client)
    draft_id = client.post(
        "/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT},
    ).json()["task_id"]
    pub_id = client.post(
        "/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT},
    ).json()["task_id"]
    fields = client.post(f"/api/tasks/{pub_id}/draft", headers=_h(csrf), json=META_OK)
    client.post(
        f"/api/tasks/{pub_id}/confirm", headers=_h(csrf),
        json={"preview_hash": fields.json()["preview_hash"]},
    )

    listed = client.get("/api/tasks", headers=HOST)
    assert listed.status_code == 200
    data = listed.json()
    published_ids = {t["id"] for t in data["published"]}
    draft_ids = {t["id"] for t in data["drafts"]}
    assert pub_id in published_ids and draft_id in draft_ids
    assert draft_id not in published_ids and pub_id not in draft_ids
    pub_item = next(t for t in data["published"] if t["id"] == pub_id)
    assert pub_item["issue_url"] == ISSUE_URL

    discarded = client.post(f"/api/tasks/{draft_id}/discard", headers=_h(csrf), json={})
    assert discarded.status_code == 200
    assert discarded.json()["status"] == "cancelado"
    rows = repo.fetch("SELECT status FROM drafts WHERE task_id = ?", (draft_id,))
    assert rows and rows[0][0] == "cancelado"
    audits = repo.fetch("SELECT action FROM audit_log WHERE action = ?", ("draft.discard",))
    assert audits

    again = client.post(f"/api/tasks/{draft_id}/discard", headers=_h(csrf), json={})
    assert again.status_code == 200
    assert again.json()["status"] == "cancelado"
    count = repo.fetch("SELECT count(*) FROM drafts WHERE task_id = ?", (draft_id,))
    assert count[0][0] == 1

    listed2 = client.get("/api/tasks", headers=HOST)
    assert draft_id not in {t["id"] for t in listed2.json()["drafts"]}
    assert draft_id not in {t["id"] for t in listed2.json()["tasks"]}
    assert pub_id in {t["id"] for t in listed2.json()["published"]}

    published_discard = client.post(f"/api/tasks/{pub_id}/discard", headers=_h(csrf), json={})
    assert published_discard.status_code == 409
    assert published_discard.json()["error"] == "draft_published"


def test_generate_cites_related_completed_issues_not_vault_notes(tmp_path):
    vault_secret = "VAULT_NOTE_FORA_DO_PROMPT_xyz"
    (tmp_path / "vault" / "Forge").mkdir(parents=True)
    (tmp_path / "vault" / "Forge" / "segredo.md").write_text("# " + vault_secret, encoding="utf-8")
    llm = FakeLLM()
    client, repo, _ = _app(tmp_path, provider=llm)
    upsert(repo, {
        "repo": REPO, "number": 34, "title": "fix: login recusa senha",
        "body": "tela de autenticacao com senha valida",
        "labels": {"names": ["Bug"]},
        "prs": [{"number": 12, "url": "https://github.com/ferreiraeborzone/site/pull/12", "files": ["auth.py"]}],
        "closed_at": "2026-11-01T00:00:00Z",
        "url": "https://github.com/ferreiraeborzone/site/issues/34",
    })
    csrf = _login(client)
    gen = client.post("/api/tasks/generate", headers=_h(csrf), json={"repo": REPO, "context": CONTEXT})
    assert gen.status_code == 200
    body = gen.json()["body"]
    assert "## Issues relacionadas" in body
    assert "ferreiraeborzone/site#34" in body
    assert "https://github.com/ferreiraeborzone/site/issues/34" in body
    assert vault_secret not in body
    assert llm.prompts
    prompt = llm.prompts[0]
    assert "ISSUES_CONCLUIDAS_RELACIONADAS" in prompt
    assert vault_secret not in prompt
    assert "Forge/segredo" not in prompt


def test_discard_requires_editor_and_csrf(tmp_path):
    client, _repo, _ = _app(tmp_path, editor=False)
    csrf = _login(client)
    forbidden = client.post("/api/tasks/x/discard", headers=_h(csrf), json={})
    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "forbidden"

    client2, _repo2, _ = _app(tmp_path / "c")
    _csrf(client2)
    no_csrf = client2.post("/api/tasks/x/discard", headers=HOST, json={})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"] == "csrf"
