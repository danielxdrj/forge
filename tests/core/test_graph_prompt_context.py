"""graph_prompt_section: contexto enxuto do grafo Graphify para prompts do motor."""
from __future__ import annotations

import json

from forge_core.graphs.prompt_context import graph_prompt_section
from forge_core.graphs.store import copy_graph

REPO = "ferreiraeborzone/site"


def _seed(tmp_path):
    nodes = [
        {"id": "f1", "label": "auth.py", "kind": "file", "file": "auth.py"},
        {"id": "fn1", "label": "login_usuario", "kind": "function", "file": "auth.py"},
        {"id": "fn2", "label": "logout_usuario", "kind": "function", "file": "auth.py"},
        {"id": "f2", "label": "relatorio.py", "kind": "file", "file": "relatorio.py"},
    ]
    edges = [
        {"source": "f1", "target": "fn1", "relation": "contains"},
        {"source": "fn1", "target": "fn2", "relation": "calls"},
    ]
    raw = tmp_path / "g.json"
    raw.write_text(json.dumps({"nodes": nodes, "edges": edges}), encoding="utf-8")
    graphs = tmp_path / "graphs"
    copy_graph(raw, graphs, REPO)
    return graphs


def test_empty_without_graph_dir():
    assert graph_prompt_section(None, "problema de login", [REPO]) == ""


def test_empty_without_repos(tmp_path):
    graphs = _seed(tmp_path)
    assert graph_prompt_section(graphs, "problema de login", []) == ""


def test_empty_when_no_token_matches(tmp_path):
    graphs = _seed(tmp_path)
    assert graph_prompt_section(graphs, "xyzxyz", [REPO]) == ""


def test_finds_relevant_node_and_neighbor(tmp_path):
    graphs = _seed(tmp_path)
    section = graph_prompt_section(graphs, "falha ao fazer login do usuario", [REPO])
    assert section.startswith("## Contexto do grafo")
    assert "login_usuario" in section
    assert "auth.py" in section
    assert "relatorio.py" not in section
    assert "vizinhos" in section


def test_respects_max_nodes(tmp_path):
    graphs = _seed(tmp_path)
    section = graph_prompt_section(graphs, "login usuario logout", [REPO], max_nodes=1)
    lines = [l for l in section.splitlines() if l.startswith("- `")]
    assert len(lines) <= 1


def test_respects_max_chars(tmp_path):
    graphs = _seed(tmp_path)
    section = graph_prompt_section(graphs, "login usuario logout", [REPO], max_chars=40)
    assert len(section.encode("utf-8")) <= 40 + len("\n[truncado]\n")


def test_unknown_repo_is_silent(tmp_path):
    graphs = _seed(tmp_path)
    assert graph_prompt_section(graphs, "login", ["outro/repo"]) == ""


def test_never_includes_vault_or_note_content(tmp_path):
    graphs = _seed(tmp_path)
    section = graph_prompt_section(graphs, "login usuario", [REPO])
    assert "vault:" not in section
    assert "note:" not in section
