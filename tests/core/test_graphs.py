"""Índice Graphify: gh e graphify falsos, sem rede, lock, HEAD e extract."""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap
from forge_core.auth.store import AuthStore
from forge_core.config import load_settings
from forge_core.draft.github_gh import GhCli
from forge_core.graphs.indexer import GraphIndexer
from forge_core.storage import open_repository
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

HOST = {"Host": "127.0.0.1:8091"}
REPO = "ferreiraeborzone/site"
DOCS = "ferreiraeborzone/ferreiraeborzone_docs"
GRAPH = {
    "nodes": [
        {"id": "n1", "label": "login_ok", "kind": "function", "file": "auth.py"},
        {"id": "n2", "label": "other", "kind": "function", "file": "x.py"},
    ],
    "edges": [{"source": "n1", "target": "n2"}],
}


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


def _gh_runner():
    def runner(argv, **kwargs):
        cmd = argv[1:]
        if cmd[:2] == ["release", "view"]:
            stdout = json.dumps({"tagName": "v1.0.0", "targetCommitish": "main"})
        elif cmd[:2] == ["repo", "clone"]:
            dest = Path(cmd[3])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "auth.py").write_text("def login_ok():\n    return True\n", encoding="utf-8")
            stdout = ""
        elif cmd[:2] == ["issue", "list"]:
            stdout = json.dumps([
                {"number": 9, "title": "login", "url": "https://github.com/ferreiraeborzone/site/issues/9",
                 "state": "OPEN"},
            ])
        else:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
        env = kwargs.get("env") or {}
        assert "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env
        return subprocess.CompletedProcess(argv, 0, stdout=stdout.encode(), stderr=b"")
    return runner


def _graphify_runner():
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        env = kwargs.get("env") or {}
        cwd = Path(kwargs.get("cwd") or ".")
        if argv[:1] == ["git"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"abc123\n", stderr=b"")
        if argv[0].endswith("graphify") or argv[0] == "graphify":
            assert argv[1:][0] == "extract"
            assert "--code-only" in argv
            assert "--out" in argv
            assert env.get("GRAPHIFY_BACKEND") == "none"
            assert "OPENAI_API_KEY" not in env
            assert "GH_TOKEN" not in env
            out_flag = argv[argv.index("--out") + 1] if "--out" in argv else None
            dest = Path(out_flag) if out_flag else cwd
            out = dest / "graphify-out"
            out.mkdir(parents=True, exist_ok=True)
            (out / "graph.json").write_text(json.dumps(GRAPH), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
    runner.calls = calls
    return runner


def _settings(tmp_path):
    return load_settings({
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'g.db'}",
        "FORGE_GRAPH_DIR": str(tmp_path / "graphs"),
        "FORGE_GRAPH_POLL_SECONDS": "0",
        "FORGE_GRAPHIFY_BIN": "graphify",
    })


def test_indexer_extracts_code_only_offline_and_queries_nodes(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    gh = GhCli(runner=_gh_runner())
    indexer = GraphIndexer(repo, settings, gh=gh, runner=_graphify_runner(), clock=lambda: "2026-11-12T00:00:00+00:00")
    result = indexer.refresh(REPO, reason="test")
    assert result["repos"][0]["status"] == "ok"
    assert result["repos"][0]["tag"] == "v1.0.0"
    assert result["state"] == "idle"
    status = {row["repo"]: row for row in indexer.status()}
    assert status[REPO]["tag"] == "v1.0.0"
    assert status[REPO]["nodes"] == 2
    assert status[REPO]["edges"] == 1
    nodes = indexer.query(REPO, "login")
    assert nodes["nodes"][0]["label"] == "login_ok"
    again = indexer.refresh(REPO, reason="test")
    assert again["repos"][0]["status"] == "unchanged"


def test_busy_lock_and_web_refresh_owner_only(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    gh = GhCli(runner=_gh_runner())
    indexer = GraphIndexer(repo, settings, gh=gh, runner=_graphify_runner())
    indexer.refresh(REPO, reason="seed")
    app = create_app(
        repo, settings, transport=Scripted(), gh=gh, graph_indexer=indexer,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    r = client.get("/api/health", headers=HOST)
    csrf = client.cookies.get(CSRF_COOKIE)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    client.get("/api/auth/login/status", headers=HOST)
    assert client.cookies.get(SESSION_COOKIE)
    listed = client.get("/api/graphs", headers=HOST)
    assert listed.status_code == 200
    assert listed.json()["graphs"]
    queried = client.get("/api/graphs/nodes", headers=HOST, params={"repo": REPO, "q": "login"})
    assert queried.status_code == 200
    assert queried.json()["nodes"][0]["label"] == "login_ok"
    csrf = client.cookies.get(CSRF_COOKIE) or csrf
    blocked = client.post("/api/graphs/refresh", headers=HOST, json={"repo": REPO})
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "csrf"
    ok = client.post(
        "/api/graphs/refresh",
        headers={**HOST, CSRF_HEADER: csrf},
        json={"repo": REPO},
    )
    assert ok.status_code == 200
    assert ok.json().get("error") != "busy"
    for _ in range(80):
        if not indexer.busy:
            break
        time.sleep(0.05)
    audits = [a.action for a in repo.list_audit()]
    assert "graph.refresh" in audits


def test_vault_api_disabled_without_config(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    app = create_app(repo, settings, transport=Scripted())
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    client.get("/api/health", headers=HOST)
    csrf = client.cookies.get(CSRF_COOKIE)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    client.get("/api/auth/login/status", headers=HOST)
    listed = client.get("/api/vault", headers=HOST)
    assert listed.status_code == 200
    assert listed.json()["enabled"] is False
    notes = client.get("/api/vault/notes", headers=HOST)
    assert notes.json()["enabled"] is False


def _gh_head_runner(sha_box, *, branch="main"):
    def runner(argv, **kwargs):
        cmd = argv[1:]
        env = kwargs.get("env") or {}
        assert "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env
        blob = " ".join(cmd)
        if cmd[:2] == ["release", "view"]:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"release not found\n")
        if cmd[:2] == ["api", "graphql"] and "defaultBranchRef" in blob:
            stdout = json.dumps({
                "data": {
                    "repository": {
                        "defaultBranchRef": {
                            "name": branch,
                            "target": {"oid": sha_box["sha"]},
                        }
                    }
                }
            })
            return subprocess.CompletedProcess(argv, 0, stdout=stdout.encode(), stderr=b"")
        if cmd[:2] == ["repo", "clone"]:
            dest = Path(cmd[3])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "README.md").write_text("docs\n", encoding="utf-8")
            assert "--branch" in cmd
            assert branch in cmd
            for banned in ("issue create", "pr create", "item-edit"):
                assert banned not in " ".join(cmd)
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
    return runner


def test_no_release_falls_back_to_default_branch_head(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    sha_box = {"sha": "aaa1111bbb2222ccc3333ddd4444eee5555fff66"}
    gh = GhCli(runner=_gh_head_runner(sha_box))
    g_runner = _graphify_runner()
    indexer = GraphIndexer(repo, settings, gh=gh, runner=g_runner, clock=lambda: "2026-11-12T00:00:00+00:00")
    result = indexer.refresh(DOCS, reason="poll")
    assert result["repos"][0]["status"] == "ok"
    assert result["repos"][0]["source"] == "head"
    assert result["repos"][0]["ref"] == "main"
    assert result["repos"][0]["commit"] == sha_box["sha"]
    status = {row["repo"]: row for row in indexer.status()}
    assert status[DOCS]["source"] == "head"
    assert status[DOCS]["commit"] == sha_box["sha"]
    graphify_calls = [c for c in g_runner.calls if c and (c[0] == "graphify" or str(c[0]).endswith("graphify"))]
    assert len(graphify_calls) == 1
    again = indexer.refresh(DOCS, reason="poll")
    assert again["repos"][0]["status"] == "unchanged"
    assert len([c for c in g_runner.calls if c and (c[0] == "graphify" or str(c[0]).endswith("graphify"))]) == 1
    sha_box["sha"] = "bbb2222ccc3333ddd4444eee5555fff6666aaa77"
    third = indexer.refresh(DOCS, reason="poll")
    assert third["repos"][0]["status"] == "ok"
    assert third["repos"][0]["commit"] == sha_box["sha"]
    assert len([c for c in g_runner.calls if c and (c[0] == "graphify" or str(c[0]).endswith("graphify"))]) == 2
    manual = indexer.refresh(DOCS, reason="manual")
    assert manual["repos"][0]["status"] == "ok"
    assert manual["repos"][0]["source"] == "head"


def test_extract_finds_graphify_out_on_cwd_despite_out_flag(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    gh = GhCli(runner=_gh_runner())

    def runner(argv, **kwargs):
        cwd = Path(kwargs.get("cwd") or ".")
        if argv[:1] == ["git"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"abc123\n", stderr=b"")
        if argv[0].endswith("graphify") or argv[0] == "graphify":
            assert "--out" in argv
            dest = cwd / "graphify-out"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "graph.json").write_text(json.dumps(GRAPH), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")

    indexer = GraphIndexer(repo, settings, gh=gh, runner=runner)
    result = indexer.refresh(REPO, reason="test")
    assert result["repos"][0]["status"] == "ok"


def test_extract_reasons_missing_exit_invalid_too_large(tmp_path, caplog, monkeypatch):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    gh = GhCli(runner=_gh_runner())
    caplog.set_level(logging.INFO, logger="forge_core.graphs")

    def missing(argv, **kwargs):
        if argv[:1] == ["git"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"abc\n", stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    indexer = GraphIndexer(repo, settings, gh=gh, runner=missing)
    missing_run = indexer.refresh(REPO, reason="test")
    assert missing_run["repos"][0]["error"] == "missing_output"
    assert "error:missing_output" in caplog.text

    def exit_fail(argv, **kwargs):
        if argv[:1] == ["git"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"abc\n", stderr=b"")
        return subprocess.CompletedProcess(argv, 3, stdout=b"", stderr=b"boom")

    indexer = GraphIndexer(repo, settings, gh=gh, runner=exit_fail)
    exited = indexer.refresh(REPO, reason="test")
    assert exited["repos"][0]["error"] == "extract_failed"
    assert exited["repos"][0]["hint"] == "exit_code=3"
    assert "exit_code=3" in caplog.text
    assert "boom" not in caplog.text

    def bad_json(argv, **kwargs):
        cwd = Path(kwargs.get("cwd") or ".")
        if argv[:1] == ["git"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"abc\n", stderr=b"")
        dest = cwd / "graphify-out"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "graph.json").write_text("not-json", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    indexer = GraphIndexer(repo, settings, gh=gh, runner=bad_json)
    invalid = indexer.refresh(REPO, reason="test")
    assert invalid["repos"][0]["error"] == "invalid_json"
    assert "error:invalid_json" in caplog.text

    monkeypatch.setattr("forge_core.graphs.store.GRAPH_MAX_BYTES", 40)

    def huge(argv, **kwargs):
        cwd = Path(kwargs.get("cwd") or ".")
        if argv[:1] == ["git"]:
            return subprocess.CompletedProcess(argv, 0, stdout=b"abc\n", stderr=b"")
        dest = cwd / "graphify-out"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "graph.json").write_text('{"nodes":[]}' + (" " * 80), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    indexer = GraphIndexer(repo, settings, gh=gh, runner=huge)
    large = indexer.refresh(REPO, reason="test")
    assert large["repos"][0]["error"] == "too_large"
    assert "error:too_large" in caplog.text


def test_second_refresh_returns_running_not_409(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    gh = GhCli(runner=_gh_runner())
    indexer = GraphIndexer(repo, settings, gh=gh, runner=_graphify_runner())
    indexer.refresh(REPO, reason="seed")
    app = create_app(repo, settings, transport=Scripted(), gh=gh, graph_indexer=indexer)
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    client.get("/api/health", headers=HOST)
    csrf = client.cookies.get(CSRF_COOKIE)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    client.get("/api/auth/login/status", headers=HOST)
    csrf = client.cookies.get(CSRF_COOKIE) or csrf
    indexer._lock.acquire()
    try:
        payload = indexer.refresh(REPO)
        assert payload["busy"] is True
        assert payload["state"] == "running"
        listed = client.get("/api/graphs/status", headers=HOST)
        assert listed.status_code == 200
        assert listed.json()["busy"] is True
        again = client.post(
            "/api/graphs/refresh",
            headers={**HOST, CSRF_HEADER: csrf},
            json={"repo": REPO},
        )
        assert again.status_code == 200
        assert again.json()["state"] == "running"
        assert again.json().get("error") != "busy"
    finally:
        indexer._lock.release()
