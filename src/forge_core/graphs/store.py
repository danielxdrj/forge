"""Leitura de graph.json + meta no volume `forge_graphs`. Sem conteúdo em log."""
from __future__ import annotations

import json
from pathlib import Path

QUERY_MAX = 200
RESULT_LIMIT = 50
GRAPH_MAX_BYTES = 32 * 1024 * 1024


def slug_for(repo: str) -> str:
    owner, _, name = repo.partition("/")
    return f"{owner}__{name}"


def repo_dir(root: Path, repo: str) -> Path:
    return root / slug_for(repo)


def read_meta(root: Path, repo: str) -> dict | None:
    path = repo_dir(root, repo) / "meta.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_meta(root: Path, repo: str, meta: dict) -> None:
    dest = repo_dir(root, repo)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "meta.json"
    tmp = dest / ".meta.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def copy_graph(src: Path, root: Path, repo: str) -> Path:
    dest_dir = repo_dir(root, repo)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "graph.json"
    data = src.read_bytes()
    if len(data) > GRAPH_MAX_BYTES:
        raise ValueError("graph_too_large")
    tmp = dest_dir / ".graph.tmp"
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def graph_counts(root: Path, repo: str) -> tuple[int, int]:
    data = load_graph(root, repo)
    if data is None:
        return 0, 0
    nodes, edges = _nodes_edges(data)
    return len(nodes), len(edges)


def load_graph(root: Path, repo: str) -> dict | None:
    path = repo_dir(root, repo) / "graph.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        size = path.stat().st_size
        if size > GRAPH_MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def nodes_for_files(root: Path, repo: str, files: list[str], limit: int = 12) -> list[dict]:
    """Nós cujo arquivo coincide com a lista (sem embeddings)."""
    want = {f.replace("\\", "/").casefold() for f in files if str(f).strip()}
    if not want:
        return []
    data = load_graph(root, repo)
    if data is None:
        return []
    nodes, _edges = _nodes_edges(data)
    out: list[dict] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        path = str(node.get("file") or node.get("path") or "").replace("\\", "/")
        if not path:
            continue
        key = path.casefold()
        if key not in want and not any(key.endswith("/" + w) or w.endswith("/" + key) for w in want):
            continue
        public = _public_node(node)
        ident = public.get("id") or f"{public.get('file')}:{public.get('label')}"
        if ident in seen:
            continue
        seen.add(ident)
        out.append(public)
        if len(out) >= limit:
            break
    return out


def query_nodes(root: Path, repo: str, question: str) -> list[dict]:
    needle = (question or "").strip()
    if not needle or len(needle) > QUERY_MAX:
        return []
    data = load_graph(root, repo)
    if data is None:
        return []
    nodes, _edges = _nodes_edges(data)
    want = needle.casefold()
    out: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        hay = " ".join(_node_terms(node)).casefold()
        if want not in hay:
            continue
        out.append(_public_node(node))
        if len(out) >= RESULT_LIMIT:
            break
    return out


def _nodes_edges(data: dict) -> tuple[list, list]:
    graph = data.get("graph") if isinstance(data.get("graph"), dict) else data
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    if isinstance(edges, dict):
        edges = list(edges.values())
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return nodes, edges


def _node_terms(node: dict) -> list[str]:
    keys = ("id", "label", "name", "type", "kind", "file", "path")
    terms = []
    for key in keys:
        value = node.get(key)
        if value is None:
            continue
        terms.append(str(value))
    return terms


def _public_node(node: dict) -> dict:
    return {
        "id": str(node.get("id") or ""),
        "label": str(node.get("label") or node.get("name") or node.get("id") or ""),
        "kind": str(node.get("kind") or node.get("type") or ""),
        "file": str(node.get("file") or node.get("path") or ""),
    }
