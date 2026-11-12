"""Leitura de graph.json + meta no volume `forge_graphs`. Sem conteúdo em log."""
from __future__ import annotations

import json
from pathlib import Path

QUERY_MAX = 200
RESULT_LIMIT = 50
GRAPH_MAX_BYTES = 96 * 1024 * 1024
GRAPH_MAX_NODES = 250_000
GRAPH_MAX_EDGES = 1_000_000


class GraphFileError(Exception):
    """Falha ao copiar/validar graph.json. Código fixo; sem conteúdo."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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


def locate_graph_json(*roots: Path) -> Path | None:
    """Primeiro graph.json regular (não symlink) sob os destinos do extract."""
    for root in roots:
        if root is None:
            continue
        for candidate in (root / "graphify-out" / "graph.json", root / "graph.json"):
            try:
                if candidate.is_file() and not candidate.is_symlink():
                    return candidate
            except OSError:
                continue
    return None


def inspect_graph_file(path: Path) -> str | None:
    """Código de erro ou None. Nunca lê o conteúdo para log."""
    try:
        size = path.stat().st_size
    except OSError:
        return "missing_output"
    if size > GRAPH_MAX_BYTES:
        return "too_large"
    if size < 2:
        return "invalid_json"
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "invalid_json"
    return inspect_graph_data(data)


def inspect_graph_data(data) -> str | None:
    """Valida o formato Graphify/NetworkX. Motivo curto, sem conteúdo."""
    if not isinstance(data, dict):
        return "schema:not_object"
    graph = graph_document(data)
    if graph is None:
        return "schema:missing_nodes"
    nodes = _as_seq(graph.get("nodes"))
    if nodes is None:
        return "schema:nodes_not_list"
    if len(nodes) == 0:
        return "schema:empty_nodes"
    if len(nodes) > GRAPH_MAX_NODES:
        return "schema:too_many_nodes"
    edges = edge_seq(graph)
    if edges is None:
        return "schema:edges_not_list"
    if len(edges) > GRAPH_MAX_EDGES:
        return "schema:too_many_edges"
    return None


def graph_document(data: dict) -> dict | None:
    """Raiz com `nodes`: Graphify grava metadados em `graph`, nós no topo."""
    if not isinstance(data, dict):
        return None
    if "nodes" in data:
        return data
    inner = data.get("graph")
    if isinstance(inner, dict) and "nodes" in inner:
        return inner
    return None


def edge_seq(graph: dict) -> list | None:
    """`links` (NetworkX node_link_data) ou `edges`. Ausente = lista vazia."""
    if "links" in graph:
        raw = graph.get("links")
    elif "edges" in graph:
        raw = graph.get("edges")
    else:
        return []
    return _as_seq(raw)


def _as_seq(raw) -> list | None:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return list(raw.values())
    return None


def has_valid_indexed_graph(root: Path, repo: str) -> bool:
    """graph.json no volume, schema ok e pelo menos um nó."""
    path = repo_dir(root, repo) / "graph.json"
    if not path.is_file() or path.is_symlink():
        return False
    if inspect_graph_file(path):
        return False
    nodes, _edges = graph_counts(root, repo)
    return nodes > 0


def copy_graph(src: Path, root: Path, repo: str) -> Path:
    reason = inspect_graph_file(src)
    if reason:
        raise GraphFileError(reason)
    dest_dir = repo_dir(root, repo)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "graph.json"
    data = src.read_bytes()
    if len(data) > GRAPH_MAX_BYTES:
        raise GraphFileError("too_large")
    tmp = dest_dir / ".graph.tmp"
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def graph_counts(root: Path, repo: str) -> tuple[int, int]:
    data = load_graph(root, repo)
    if data is None:
        return 0, 0
    nodes, edges = nodes_edges(data)
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


def graph_mtime_ns(root: Path, repo: str) -> int:
    return graph_stamp(root, repo)[0]


def graph_stamp(root: Path, repo: str) -> tuple[int, int]:
    """mtime_ns e tamanho do graph.json. (0, 0) se faltar. Sem ler o conteúdo."""
    path = repo_dir(root, repo) / "graph.json"
    try:
        if path.is_file() and not path.is_symlink():
            st = path.stat()
            return int(st.st_mtime_ns), int(st.st_size)
    except OSError:
        return (0, 0)
    return (0, 0)


def nodes_for_files(root: Path, repo: str, files: list[str], limit: int = 12) -> list[dict]:
    """Nós cujo arquivo coincide com a lista (sem embeddings)."""
    want = {f.replace("\\", "/").casefold() for f in files if str(f).strip()}
    if not want:
        return []
    data = load_graph(root, repo)
    if data is None:
        return []
    nodes, _edges = nodes_edges(data)
    out: list[dict] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        path = _node_file(node)
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
    nodes, _edges = nodes_edges(data)
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


def nodes_edges(data: dict) -> tuple[list, list]:
    graph = graph_document(data) or {}
    nodes = _as_seq(graph.get("nodes")) or []
    edges = edge_seq(graph) or []
    return nodes, edges


def _nodes_edges(data: dict) -> tuple[list, list]:
    return nodes_edges(data)


def _node_file(node: dict) -> str:
    return str(node.get("file") or node.get("path") or node.get("source_file") or "").replace("\\", "/")


def _node_terms(node: dict) -> list[str]:
    keys = ("id", "label", "name", "type", "kind", "file", "path", "source_file")
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
        "file": _node_file(node),
    }
