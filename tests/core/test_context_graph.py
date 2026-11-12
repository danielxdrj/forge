"""API /api/context-graph: papéis, agregação, vault, sem conteúdo de nota."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, bootstrap, person
from forge_core.auth.store import AuthStore
from forge_core.config import load_settings
from forge_core.graphs.store import copy_graph, inspect_graph_file, nodes_edges, write_meta
from forge_core.issues.store import upsert
from forge_core.notes.service import NoteService
from forge_core.obsidian.vault import ObsidianVault
from forge_core.storage import open_repository
from forge_core.storage.seed import seed_allowed_repos
from forge_core.web.app import create_app
from forge_core.web.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

HOST = {"Host": "127.0.0.1:8091"}
REPO = "ferreiraeborzone/site"
FIXTURE = Path(__file__).parent / "fixtures" / "graphify_graph.json"
ISSUE_URL = "https://github.com/ferreiraeborzone/site/issues/34"
PR_URL = "https://github.com/ferreiraeborzone/site/pull/12"
SENTINEL = "SENTINELA_TEIA_NAO_VAZAR ghp_" + ("A" * 36)


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


def _settings(tmp_path, extra=None):
    env = {
        "FORGE_CONFIG_DIR": str(tmp_path),
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'c.db'}",
        "FORGE_GRAPH_DIR": str(tmp_path / "graphs"),
        "FORGE_GRAPH_POLL_SECONDS": "0",
        "FORGE_GRAPH_NODE_LIMIT": "500",
        "FORGE_GRAPH_EDGE_LIMIT": "1500",
    }
    if extra:
        env.update(extra)
    return load_settings(env)


def _login(client):
    client.get("/api/health", headers=HOST)
    csrf = client.cookies.get(CSRF_COOKIE)
    client.post("/api/auth/login/start", headers={**HOST, CSRF_HEADER: csrf})
    status = client.get("/api/auth/login/status", headers=HOST)
    assert status.json()["status"] == "authorized"
    assert client.cookies.get(SESSION_COOKIE)
    return client.cookies.get(CSRF_COOKIE) or csrf


def _seed_graph(tmp_path, functions=3):
    nodes = [
        {"id": "f1", "label": "auth.py", "kind": "file", "file": "auth.py"},
        {"id": "c1", "label": "Auth", "kind": "class", "file": "auth.py"},
    ]
    edges = [
        {"source": "f1", "target": "c1", "relation": "contains"},
        {"source": "f1", "target": "f1", "relation": "imports"},
    ]
    for i in range(functions):
        nid = f"fn{i}"
        nodes.append({"id": nid, "label": f"login_{i}", "kind": "function", "file": "auth.py"})
        edges.append({"source": "c1", "target": nid, "relation": "contains"})
        if i:
            edges.append({"source": f"fn{i-1}", "target": nid, "relation": "calls"})
    for i in range(24):
        fid = f"x{i}"
        nodes.append({"id": fid, "label": f"mod{i}.py", "kind": "file", "file": f"mod{i}.py"})
        edges.append({"source": fid, "target": "f1", "relation": "imports"})
    raw = tmp_path / "g.json"
    raw.write_text(json.dumps({"nodes": nodes, "edges": edges}), encoding="utf-8")
    graphs = tmp_path / "graphs"
    copy_graph(raw, graphs, REPO)
    write_meta(graphs, REPO, {"tag": "v1", "commit": "abc123", "source": "release"})


def _seed_issue_and_note(repo, principal):
    upsert(repo, {
        "repo": REPO, "number": 34, "title": "fix login",
        "body": SENTINEL,
        "labels": {"names": ["Bug"]},
        "prs": [{"number": 12, "url": PR_URL, "files": ["auth.py"]}],
        "closed_at": "2026-11-01T00:00:00Z", "url": ISSUE_URL,
    })
    notes = NoteService(repo, AuthStore(repo))
    return notes.create(principal, {
        "issue_key": f"{REPO}#34", "title": "Pista login", "body": SENTINEL,
    })


def test_context_graph_requires_editor_or_owner(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    app = create_app(repo, settings, transport=Scripted())
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    anon = client.get("/api/context-graph", headers=HOST)
    assert anon.status_code == 401
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    person(repo, owner, FakeGitHub(), "solta", 1004)
    other = create_app(repo, settings, transport=Scripted(user=(1004, "solta")))
    c2 = TestClient(other, base_url="http://127.0.0.1:8091")
    _login(c2)
    denied = c2.get("/api/context-graph", headers=HOST)
    assert denied.status_code == 403
    assert SENTINEL not in denied.text


def test_context_graph_aggregates_limits_no_vault_no_content(tmp_path):
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    _seed_graph(tmp_path, functions=40)
    _seed_issue_and_note(repo, owner)
    app = create_app(repo, settings, transport=Scripted())
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    _login(client)
    full = client.get("/api/context-graph", headers=HOST, params={"repo": REPO})
    assert full.status_code == 200
    payload = full.json()
    assert payload["vault"] is False
    types = {n["type"] for n in payload["nodes"]}
    assert "issue" in types
    assert "pr" in types
    assert "note" in types
    assert "file" in types
    assert "vault" not in types
    assert "function" not in types
    dump = json.dumps(payload)
    assert SENTINEL not in dump
    assert "body" not in dump
    assert any(e["type"] == "touches" for e in payload["edges"])
    assert any(e["type"] == "pr" for e in payload["edges"])
    assert any(e["type"] == "notes" for e in payload["edges"])
    small = client.get(
        "/api/context-graph", headers=HOST,
        params={"repo": REPO, "limit": 10},
    )
    assert small.status_code == 200
    slim = small.json()
    assert slim["truncated"] is True
    assert len(slim["nodes"]) <= 10
    ids = {n["type"] for n in slim["nodes"]}
    assert "issue" in ids or "note" in ids
    typed = client.get(
        "/api/context-graph", headers=HOST,
        params={"repo": REPO, "types": "issue,note"},
    )
    assert typed.status_code == 200
    assert {n["type"] for n in typed.json()["nodes"]} <= {"issue", "note"}
    searched = client.get(
        "/api/context-graph", headers=HOST,
        params={"repo": REPO, "q": "Pista"},
    )
    assert searched.status_code == 200
    assert any("Pista" in (n.get("label") or "") for n in searched.json()["nodes"])
    audits = repr(repo.list_audit())
    assert SENTINEL not in audits


def test_context_graph_vault_wiki_links_without_content(tmp_path):
    vault_root = tmp_path / "vault"
    (vault_root / "Forge").mkdir(parents=True)
    (vault_root / "Inbox").mkdir()
    (vault_root / "Forge" / "ok.md").write_text(
        "---\ntitle: Nota ok\n---\nVer [[Inbox/x]]\n" + SENTINEL,
        encoding="utf-8",
    )
    (vault_root / "Inbox" / "x.md").write_text("# Inbox\n" + SENTINEL + "\n", encoding="utf-8")
    (vault_root / "Secret").mkdir()
    (vault_root / "Secret" / "hidden.md").write_text("segredo " + SENTINEL, encoding="utf-8")
    settings = _settings(tmp_path, {
        "FORGE_OBSIDIAN_VAULT": str(vault_root.resolve()),
        "FORGE_OBSIDIAN_ALLOW": "Forge,Inbox",
    })
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    _seed_graph(tmp_path, functions=2)
    obsidian = ObsidianVault.from_settings(settings)
    app = create_app(repo, settings, transport=Scripted(), obsidian=obsidian)
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    _login(client)
    res = client.get("/api/context-graph", headers=HOST)
    assert res.status_code == 200
    data = res.json()
    assert data["vault"] is True
    vault_nodes = [n for n in data["nodes"] if n["type"] == "vault"]
    paths = {n["path"] for n in vault_nodes}
    assert "Forge/ok.md" in paths
    assert "Inbox/x.md" in paths
    assert not any("Secret" in p for p in paths)
    for node in vault_nodes:
        assert set(node).issubset({"id", "type", "label", "path", "repo", "url"})
        assert "body" not in node
    wiki = [e for e in data["edges"] if e["type"] == "wiki"]
    assert wiki
    dump = json.dumps(data)
    assert SENTINEL not in dump
    assert "segredo" not in dump


def test_real_graphify_fixture_parses_and_builds_context_graph(tmp_path):
    assert FIXTURE.is_file()
    assert inspect_graph_file(FIXTURE) is None
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    nodes, edges = nodes_edges(raw)
    assert len(nodes) > 0
    assert len(edges) > 0
    assert any(n.get("source_file") for n in nodes if isinstance(n, dict))
    assert any("source" in e and "target" in e for e in edges if isinstance(e, dict))
    settings = _settings(tmp_path)
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub(), login_name="dona", github_id=1000)
    AuthStore(repo).grant_role(owner, 1000, "editor")
    copy_graph(FIXTURE, tmp_path / "graphs", REPO)
    write_meta(tmp_path / "graphs", REPO, {
        "tag": "v1", "commit": "abc123", "source": "release", "status": "ok", "nodes": len(nodes),
    })
    app = create_app(repo, settings, transport=Scripted())
    client = TestClient(app, base_url="http://127.0.0.1:8091")
    _login(client)
    res = client.get("/api/context-graph", headers=HOST, params={"repo": REPO})
    assert res.status_code == 200
    payload = res.json()
    code = [n for n in payload["nodes"] if n["type"] in {"file", "module", "class"}]
    assert len(code) > 0
    labels = {n["label"] for n in code}
    assert "auth.py" in labels or "AuthService" in labels or "app.py" in labels
