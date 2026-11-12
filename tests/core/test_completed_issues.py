"""Importador de issues concluídas: gh falso, upsert, redação, vault, ranking, API."""
from __future__ import annotations

import json
import logging
import subprocess

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap, person
from forge_core.auth.store import AuthStore
from forge_core.config import load_settings
from forge_core.draft.github_gh import GhCli
from forge_core.graphs.indexer import GraphIndexer
from forge_core.graphs.store import copy_graph, write_meta
from forge_core.issues.importer import CompletedIssueImporter
from forge_core.issues.related import find_related
from forge_core.issues.store import get_one, list_all, upsert
from forge_core.storage import open_repository
from forge_core.storage.migrate import pending_migrations
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

HOST = {"Host": "127.0.0.1:8091"}
REPO = "ferreiraeborzone/site"
ISSUE_URL = "https://github.com/ferreiraeborzone/site/issues/34"
PR_URL = "https://github.com/ferreiraeborzone/site/pull/12"
GHP = "ghp_" + ("A" * 36)
SENTINEL = "SENTINELA_ISSUE_BODY_NAO_LOGAR " + GHP
TITLE = "fix: login recusa senha valida"


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


def _issue_detail():
    return {
        "data": {
            "repository": {
                "issue": {
                    "number": 34,
                    "title": TITLE,
                    "body": "Corrigir login.\n" + SENTINEL,
                    "url": ISSUE_URL,
                    "closedAt": "2026-11-01T12:00:00Z",
                    "state": "CLOSED",
                    "labels": {"nodes": [{"name": "Bug"}, {"name": "tipo:Bug"}]},
                    "closedByPullRequestsReferences": {
                        "nodes": [{"number": 12, "url": PR_URL, "title": "fix login"}],
                    },
                }
            }
        }
    }


def _done_page():
    return {
        "data": {
            "node": {
                "items": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [{
                        "fieldValues": {
                            "nodes": [
                                {"name": "Done", "field": {"name": "Status"}},
                                {"name": "Bug", "field": {"name": "Tipo"}},
                                {"name": "Alta", "field": {"name": "Prioridade"}},
                                {"title": "Semana 45", "field": {"name": "Sprint"}},
                            ]
                        },
                        "content": {
                            "number": 34,
                            "title": TITLE,
                            "url": ISSUE_URL,
                            "closedAt": "2026-11-01T12:00:00Z",
                            "repository": {"nameWithOwner": REPO},
                            "labels": {"nodes": [{"name": "Bug"}]},
                        },
                    }],
                }
            }
        }
    }


def _repo_arg(cmd: list[str]) -> str:
    if "--repo" in cmd:
        return cmd[cmd.index("--repo") + 1]
    return ""


def _gh_runner():
    def runner(argv, **kwargs):
        cmd = argv[1:]
        env = kwargs.get("env") or {}
        assert "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env
        blob = " ".join(cmd)
        repo = _repo_arg(cmd)
        if cmd[:2] == ["auth", "status"]:
            stdout = "Logged in to github.com as forge\nToken scopes: 'repo', 'project'\n"
        elif cmd[:2] == ["project", "view"]:
            stdout = json.dumps({"id": "PVT_proj", "title": "IT Backlog", "number": 13})
        elif cmd[:2] == ["issue", "list"] and "--state" in cmd:
            if repo != REPO:
                stdout = "[]"
            else:
                stdout = json.dumps([{
                    "number": 34, "title": TITLE, "url": ISSUE_URL,
                    "closedAt": "2026-11-01T12:00:00Z", "state": "CLOSED",
                    "labels": [{"name": "Bug"}],
                }])
        elif cmd[:2] == ["api", "graphql"]:
            if "closedByPullRequestsReferences" in blob:
                stdout = json.dumps(_issue_detail())
            else:
                stdout = json.dumps(_done_page())
        elif cmd[:2] == ["pr", "view"]:
            stdout = json.dumps({"number": 12, "url": PR_URL, "files": [{"path": "auth.py"}]})
        elif cmd[:2] == ["issue", "view"]:
            stdout = json.dumps({
                "number": 34, "title": TITLE, "body": "fallback", "url": ISSUE_URL,
                "closedAt": "2026-11-01T12:00:00Z", "labels": [{"name": "Bug"}], "state": "CLOSED",
            })
        else:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
        for banned in ("issue create", "pr create", "item-edit", "item-add"):
            assert banned not in " ".join(cmd)
        return subprocess.CompletedProcess(argv, 0, stdout=stdout.encode(), stderr=b"")
    return runner


def _settings(tmp_path, extra=None):
    env = {
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'c.db'}",
        "FORGE_GRAPH_DIR": str(tmp_path / "graphs"),
        "FORGE_GRAPH_POLL_SECONDS": "0",
    }
    if extra:
        env.update(extra)
    return load_settings(env)


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


def test_0017_listed_for_both_dialects(make_repo):
    sqlite = [p.stem for p in pending_migrations("sqlite")]
    postgres = [p.stem for p in pending_migrations("postgres")]
    assert any(s.startswith("0017_completed_issues") for s in sqlite)
    assert any(s.startswith("0017_completed_issues") for s in postgres)
    repo = make_repo()
    repo.fetch("SELECT repo, number, title, body FROM completed_issues LIMIT 0")


def test_upsert_is_idempotent_and_updates(make_repo):
    repo = make_repo()
    first = upsert(repo, {
        "repo": REPO, "number": 34, "title": "old", "body": "a",
        "labels": {"tipo": "Bug", "prioridade": "", "sprint": "", "names": ["Bug"]},
        "prs": [], "closed_at": "2026-01-01T00:00:00Z", "url": ISSUE_URL,
    }, imported_at="t1")
    assert first.title == "old"
    second = upsert(repo, {
        "repo": REPO, "number": 34, "title": "new", "body": "b",
        "labels": {"tipo": "Bug", "prioridade": "Alta", "sprint": "", "names": ["Bug"]},
        "prs": [{"number": 12, "url": PR_URL, "files": ["auth.py"]}],
        "closed_at": "2026-11-01T00:00:00Z", "url": ISSUE_URL,
    }, imported_at="t2")
    assert second.title == "new"
    assert second.body == "b"
    rows = list_all(repo)
    assert len(rows) == 1
    assert rows[0].labels["prioridade"] == "Alta"


def test_importer_redacts_body_writes_vault_and_skips_github_writes(tmp_path, caplog):
    vault = tmp_path / "vault"
    (vault / "Forge").mkdir(parents=True)
    settings = _settings(tmp_path, {
        "FORGE_OBSIDIAN_VAULT": str(vault),
        "FORGE_OBSIDIAN_ALLOW": "Forge",
    })
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    gh = GhCli(runner=_gh_runner())
    importer = CompletedIssueImporter(repo, settings, gh=gh, clock=lambda: "2026-11-12T00:00:00+00:00")
    caplog.set_level(logging.INFO, logger="forge_core.issues")
    result = importer.run(reason="test", actor="system:test")
    assert result["imported"] == 1
    item = get_one(repo, REPO, 34)
    assert item is not None
    assert GHP not in item.body
    assert "SENTINELA_ISSUE_BODY" in item.body
    assert item.prs[0]["files"] == ["auth.py"]
    note = vault / "Forge" / "site" / "34.md"
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    assert "repo: ferreiraeborzone/site" in text
    assert GHP not in text
    assert ISSUE_URL in text
    assert PR_URL in text
    assert "auth.py" in text
    dump = caplog.text + repr(repo.list_audit())
    assert GHP not in dump
    assert SENTINEL not in dump
    calls = [" ".join(c) for c in gh.calls]
    assert not any("issue create" in c or "pr create" in c or "item-edit" in c for c in calls)

    again = importer.run(reason="test", actor="system:test")
    assert again["updated"] == 1
    assert again["imported"] == 0
    assert len(list_all(repo)) == 1


def test_related_prefers_same_repo_and_graph_nodes(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    upsert(repo, {
        "repo": REPO, "number": 34, "title": TITLE, "body": "login na tela de autenticacao",
        "labels": {"names": ["Bug"]}, "prs": [{"number": 12, "url": PR_URL, "files": ["auth.py"]}],
        "closed_at": "2026-11-01T00:00:00Z", "url": ISSUE_URL,
    })
    upsert(repo, {
        "repo": "ferreiraeborzone/sistema-cobranca-monolith", "number": 1483,
        "title": "chore: outro assunto", "body": "fatura",
        "labels": {"names": []}, "prs": [], "closed_at": None, "url": "https://github.com/ferreiraeborzone/sistema-cobranca-monolith/issues/1483",
    })
    graph = tmp_path / "g.json"
    graph.write_text(json.dumps({
        "nodes": [{"id": "n1", "label": "login_ok", "kind": "function", "file": "auth.py"}],
        "edges": [],
    }), encoding="utf-8")
    copy_graph(graph, tmp_path / "graphs", REPO)
    write_meta(tmp_path / "graphs", REPO, {"tag": "v1"})
    related = find_related(
        repo, "login recusa senha na autenticacao", REPO,
        graph_dir=tmp_path / "graphs",
    )
    assert related
    assert related[0]["number"] == 34
    assert related[0]["nodes"][0]["label"] == "login_ok"
    assert 1483 not in {r["number"] for r in related}


def test_poll_runs_importer_and_web_owner_csrf(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    gh = GhCli(runner=_gh_runner())
    importer = CompletedIssueImporter(repo, settings, gh=gh)
    called = []

    def on_poll(reason):
        called.append(reason)
        importer.run(reason=reason, actor="system:poll")

    indexer = GraphIndexer(repo, settings, gh=gh, on_poll=on_poll)
    indexer._loop()
    assert called == ["startup"]
    assert get_one(repo, REPO, 34) is not None

    app = create_app(
        repo, settings, transport=Scripted(), gh=gh, issue_importer=importer, graph_indexer=indexer,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    csrf = _login(client)
    blocked = client.post("/api/completed-issues/import", headers=HOST, json={})
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "csrf"
    ok = client.post("/api/completed-issues/import", headers=_h(csrf), json={})
    assert ok.status_code == 200
    upsert(repo, {
        "repo": REPO, "number": 35, "title": "fix: login tela autenticacao",
        "body": "senha valida", "labels": {"names": ["Bug"]}, "prs": [],
        "closed_at": "2026-11-02T00:00:00Z",
        "url": "https://github.com/ferreiraeborzone/site/issues/35",
    })
    related = client.get(
        "/api/completed-issues", headers=HOST, params={"issue": "ferreiraeborzone/site#34"},
    )
    assert related.status_code == 200
    numbers = {item["number"] for item in related.json()["issues"]}
    assert 35 in numbers
    assert 34 not in numbers
    dump = repr(repo.list_audit())
    assert GHP not in dump
    assert SENTINEL not in dump
    assert "issues.import" in [a.action for a in repo.list_audit()]


def test_editor_cannot_import(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    gh = GhCli(runner=_gh_runner())
    app = create_app(repo, settings, transport=Scripted(user=(42, "maria")), gh=gh)
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    csrf = _login(client)
    denied = client.post("/api/completed-issues/import", headers=_h(csrf), json={})
    assert denied.status_code == 403
