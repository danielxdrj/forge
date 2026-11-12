"""Grafo combinado da Teia: código Graphify, issues, PRs, notas, vault.

Payload enxuto: sem corpo de nota. Vault só com título e caminho relativo.
Nunca loga conteúdo de nota.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings
from ..issues.store import list_all as list_completed
from ..obsidian.vault import ObsidianVault, VaultRuleError
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository
from . import store
from .indexer import GraphError

log = logging.getLogger("forge_core.graphs")

NODE_TYPES = ("issue", "pr", "note", "vault", "file", "module", "class")
PRIORITY_TYPES = frozenset({"issue", "pr", "note", "vault"})
FINE_CODE = frozenset({"function", "method", "symbol", "interface", "rationale"})
KEEP_CODE = frozenset({"file", "module", "class"})
IMPORT_REL = frozenset({"imports", "imports_from", "import", "uses"})
CALL_REL = frozenset({"calls", "call"})
CONTAINS_REL = frozenset({"contains", "defines", "has", "declares"})
QUERY_MAX = store.QUERY_MAX


class ContextGraph:
    def __init__(self, repo: SqlRepository, settings: Settings, vault: ObsidianVault):
        self._repo = repo
        self._settings = settings
        self._vault = vault
        self._root = Path(settings.graph_dir)
        self._cache: tuple | None = None

    def build(
        self,
        *,
        repo: str = "",
        types: str = "",
        q: str = "",
        limit: int = 0,
    ) -> dict:
        want_repo = (repo or "").strip()
        allowed = [f"{row.owner}/{row.repo_name}" for row in list_active_allowed_repos(self._repo)]
        if want_repo:
            match = [item for item in allowed if item.lower() == want_repo.lower()]
            if len(match) != 1:
                raise GraphError("repo_not_allowed")
            repos = match
        else:
            repos = allowed
        type_filter = _parse_types(types)
        query = (q or "").strip()[:QUERY_MAX]
        node_limit = self._settings.graph_node_limit
        edge_limit = self._settings.graph_edge_limit
        if limit and limit > 0:
            node_limit = max(1, min(int(limit), node_limit))
        sig = self._signature(repos, type_filter, query, node_limit, edge_limit)
        if self._cache and self._cache[0] == sig:
            return self._cache[1]
        payload = self._compose(repos, type_filter, query, node_limit, edge_limit)
        self._cache = (sig, payload)
        return payload

    def _signature(self, repos, type_filter, query, node_limit, edge_limit) -> tuple:
        mtimes = tuple((name, store.graph_mtime_ns(self._root, name)) for name in repos)
        notes_row = self._repo.fetch("SELECT COUNT(*), MAX(updated_at) FROM investigation_notes")
        notes_sig = notes_row[0] if notes_row else (0, None)
        vault_on = bool(self._vault.enabled)
        vault_sig: tuple = ()
        if vault_on:
            try:
                listed = self._vault.list_notes()
            except VaultRuleError:
                listed = {"notes": []}
            vault_sig = tuple(
                (str(n.get("path") or ""), str(n.get("title") or ""))
                for n in (listed.get("notes") or [])
                if isinstance(n, dict)
            )
        issues_row = self._repo.fetch("SELECT COUNT(*), MAX(imported_at) FROM completed_issues")
        issues_sig = issues_row[0] if issues_row else (0, None)
        return (tuple(repos), type_filter, query, node_limit, edge_limit, mtimes, notes_sig, vault_on, vault_sig, issues_sig)

    def _compose(self, repos: list[str], type_filter: tuple[str, ...], query: str, node_limit: int, edge_limit: int) -> dict:
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edge: set[tuple[str, str, str]] = set()
        vault_enabled = bool(self._vault.enabled)

        for full in repos:
            meta = store.read_meta(self._root, full) or {}
            commit = str(meta.get("commit") or "")
            data = store.load_graph(self._root, full)
            if data is None:
                continue
            raw_nodes, raw_edges = store.nodes_edges(data)
            _add_code(full, raw_nodes, raw_edges, commit, nodes, edges, seen_edge)

        repo_set = {r.lower() for r in repos}
        for item in list_completed(self._repo):
            if item.repo.lower() not in repo_set:
                continue
            issue_id = f"issue:{item.repo}#{item.number}"
            nodes[issue_id] = _public(
                issue_id, "issue", item.title or issue_id, repo=item.repo, url=item.url or "",
            )
            files: list[str] = []
            for pr in item.prs or []:
                if not isinstance(pr, dict):
                    continue
                number = pr.get("number")
                try:
                    pr_n = int(number)
                except (TypeError, ValueError):
                    continue
                pr_id = f"pr:{item.repo}#{pr_n}"
                nodes[pr_id] = _public(
                    pr_id, "pr", f"PR #{pr_n}", repo=item.repo, url=str(pr.get("url") or ""),
                )
                _edge(edges, seen_edge, issue_id, pr_id, "pr")
                for path in pr.get("files") or []:
                    text = str(path).strip().replace("\\", "/")
                    if text:
                        files.append(text)
            for path in files:
                file_id = _ensure_file(nodes, item.repo, path, str((store.read_meta(self._root, item.repo) or {}).get("commit") or ""))
                _edge(edges, seen_edge, issue_id, file_id, "touches")

        note_rows = self._repo.fetch(
            "SELECT id, issue_key, title FROM investigation_notes ORDER BY updated_at DESC, id",
        )
        for note_id, issue_key, title in note_rows:
            repo_name, _sep, _num = (issue_key or "").partition("#")
            if repo_name.lower() not in repo_set:
                continue
            nid = f"note:{note_id}"
            nodes[nid] = _public(nid, "note", title or nid, repo=repo_name, path=None)
            issue_id = f"issue:{issue_key}"
            if issue_id not in nodes:
                url = f"https://github.com/{repo_name}/issues/{_num}" if _num.isdigit() else ""
                nodes[issue_id] = _public(issue_id, "issue", issue_key, repo=repo_name, url=url)
            _edge(edges, seen_edge, nid, issue_id, "notes")

        if vault_enabled:
            try:
                listed = self._vault.list_notes()
            except VaultRuleError as exc:
                log.info("graph.vault result=error:%s", exc.code)
                listed = {"notes": []}
            vault_notes = [n for n in (listed.get("notes") or []) if isinstance(n, dict)]
            by_path: dict[str, str] = {}
            by_stem: dict[str, str] = {}
            by_title: dict[str, str] = {}
            for note in vault_notes:
                path = str(note.get("path") or "").replace("\\", "/")
                title = str(note.get("title") or path)
                if not path:
                    continue
                vid = f"vault:{path}"
                nodes[vid] = _public(vid, "vault", title, path=path)
                by_path[path.casefold()] = vid
                by_path[path[:-3].casefold() if path.casefold().endswith(".md") else path.casefold()] = vid
                stem = path.rsplit("/", 1)[-1]
                if stem.lower().endswith(".md"):
                    stem = stem[:-3]
                by_stem.setdefault(stem.casefold(), vid)
                if title:
                    by_title.setdefault(title.casefold(), vid)
            for note in vault_notes:
                path = str(note.get("path") or "").replace("\\", "/")
                src = f"vault:{path}"
                for link in note.get("links") or []:
                    target = _resolve_wiki(str(link), by_path, by_stem, by_title)
                    if target and target != src:
                        _edge(edges, seen_edge, src, target, "wiki")

        collapse_classes = _count_code(nodes) > node_limit
        if collapse_classes:
            _collapse_classes(nodes, edges, seen_edge)

        if type_filter:
            keep_types = set(type_filter)
            nodes = {k: v for k, v in nodes.items() if v.get("type") in keep_types}
            edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]

        if query:
            nodes, edges = _filter_query(nodes, edges, query)

        truncated = False
        if len(nodes) > node_limit or len(edges) > edge_limit:
            nodes, edges, truncated = _cap(nodes, edges, node_limit, edge_limit)

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "truncated": truncated,
            "vault": vault_enabled,
            "node_limit": node_limit,
            "edge_limit": edge_limit,
        }


def _parse_types(raw: str) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        item = part.strip().lower()
        if item in NODE_TYPES and item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def _public(ident: str, typ: str, label: str, **extra) -> dict:
    data = {"id": ident, "type": typ, "label": label}
    for key, value in extra.items():
        if value not in (None, "", []):
            data[key] = value
    return data


def _edge(edges: list[dict], seen: set[tuple[str, str, str]], source: str, target: str, kind: str) -> None:
    if not source or not target or source == target:
        return
    key = (source, target, kind)
    if key in seen:
        return
    seen.add(key)
    edges.append({"source": source, "target": target, "type": kind})


def _code_kind(node: dict) -> str:
    raw = str(node.get("kind") or node.get("type") or "").strip().lower()
    if raw in KEEP_CODE or raw in FINE_CODE:
        return raw
    path = _file_of(node)
    label = str(node.get("label") or node.get("name") or "")
    if node.get("_callable_class"):
        return "class"
    if path and (label in {path, path.rsplit("/", 1)[-1]} or label.endswith((".py", ".ts", ".js", ".go", ".rs"))):
        return "file"
    if path and ("/" in label or label.endswith(tuple(f".{e}" for e in ("py", "ts", "js", "go", "rs", "md")))):
        return "file"
    if node.get("_callable") or label.endswith("()"):
        return "function"
    if raw in {"code", ""}:
        if path and not label:
            return "file"
        return "function"
    return "file"


def _file_of(node: dict) -> str:
    return str(node.get("file") or node.get("path") or node.get("source_file") or "").replace("\\", "/").lstrip("./")


def _file_id(repo: str, path: str) -> str:
    return f"file:{repo}:{path.replace('\\', '/')}"


def _ensure_file(nodes: dict[str, dict], repo: str, path: str, commit: str) -> str:
    rel = path.replace("\\", "/").lstrip("./")
    fid = _file_id(repo, rel)
    if fid not in nodes:
        url = f"https://github.com/{repo}/blob/{commit or 'HEAD'}/{rel}" if rel else ""
        nodes[fid] = _public(fid, "file", rel.rsplit("/", 1)[-1] or rel, repo=repo, path=rel, url=url)
    return fid


def _add_code(repo: str, raw_nodes: list, raw_edges: list, commit: str, nodes: dict, edges: list, seen: set) -> None:
    parent: dict[str, str] = {}
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        orig = str(node.get("id") or "")
        kind = _code_kind(node)
        path = _file_of(node)
        label = str(node.get("label") or node.get("name") or orig or path)
        if kind in FINE_CODE or kind == "function":
            if not path:
                continue
            fid = _ensure_file(nodes, repo, path, commit)
            if orig:
                parent[orig] = fid
            continue
        if kind == "class":
            cid = f"class:{repo}:{path}:{label}" if path else f"class:{repo}:{label}"
            url = f"https://github.com/{repo}/blob/{commit or 'HEAD'}/{path}" if path else ""
            nodes[cid] = _public(cid, "class", label, repo=repo, path=path or None, url=url or None)
            if orig:
                parent[orig] = cid
            if path:
                _ensure_file(nodes, repo, path, commit)
            continue
        if kind == "module":
            mid = f"module:{repo}:{label or path}"
            nodes[mid] = _public(mid, "module", label or path, repo=repo, path=path or None)
            if orig:
                parent[orig] = mid
            continue
        if path:
            fid = _ensure_file(nodes, repo, path, commit)
            if orig:
                parent[orig] = fid
        elif orig:
            fid = _ensure_file(nodes, repo, label or orig, commit)
            parent[orig] = fid

    for raw in raw_edges:
        if not isinstance(raw, dict):
            continue
        src = _endpoint(raw.get("source")) or _endpoint(raw.get("from"))
        dst = _endpoint(raw.get("target")) or _endpoint(raw.get("to"))
        rel = str(raw.get("relation") or raw.get("type") or raw.get("kind") or "").strip().lower()
        if rel in CONTAINS_REL:
            continue
        if rel in IMPORT_REL:
            kind = "imports"
        elif rel in CALL_REL:
            kind = "calls"
        else:
            kind = "calls"
        left = parent.get(src)
        right = parent.get(dst)
        if left and right:
            _edge(edges, seen, left, right, kind)


def _endpoint(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        return str(raw.get("id") or raw.get("label") or "")
    return str(raw)


def _count_code(nodes: dict[str, dict]) -> int:
    return sum(1 for n in nodes.values() if n.get("type") in KEEP_CODE)


def _collapse_classes(nodes: dict[str, dict], edges: list[dict], seen: set) -> None:
    remap: dict[str, str] = {}
    drop: set[str] = set()
    for ident, node in list(nodes.items()):
        if node.get("type") != "class":
            continue
        repo = str(node.get("repo") or "")
        path = str(node.get("path") or "")
        if not repo or not path:
            continue
        fid = _file_id(repo, path)
        if fid not in nodes:
            _ensure_file(nodes, repo, path, "")
        remap[ident] = fid
        drop.add(ident)
    for ident in drop:
        nodes.pop(ident, None)
    new_edges: list[dict] = []
    seen.clear()
    for edge in edges:
        src = remap.get(edge["source"], edge["source"])
        dst = remap.get(edge["target"], edge["target"])
        if src in nodes and dst in nodes:
            _edge(new_edges, seen, src, dst, edge["type"])
    edges[:] = new_edges


def _filter_query(nodes: dict[str, dict], edges: list[dict], query: str) -> tuple[dict[str, dict], list[dict]]:
    want = query.casefold()
    hits = set()
    for ident, node in nodes.items():
        hay = " ".join(str(node.get(k) or "") for k in ("id", "label", "path", "repo", "type")).casefold()
        if want in hay:
            hits.add(ident)
    if not hits:
        return {}, []
    keep = set(hits)
    for edge in edges:
        if edge["source"] in hits:
            keep.add(edge["target"])
        if edge["target"] in hits:
            keep.add(edge["source"])
    nodes = {k: v for k, v in nodes.items() if k in keep}
    edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    return nodes, edges


def _cap(nodes: dict[str, dict], edges: list[dict], node_limit: int, edge_limit: int) -> tuple[dict, list, bool]:
    adj: dict[str, set[str]] = {k: set() for k in nodes}
    for edge in edges:
        if edge["source"] in adj and edge["target"] in adj:
            adj[edge["source"]].add(edge["target"])
            adj[edge["target"]].add(edge["source"])
    priority = {k for k, n in nodes.items() if n.get("type") in PRIORITY_TYPES}
    connected = set()
    for ident in priority:
        connected.update(adj.get(ident, ()))
    keep: list[str] = []
    seen: set[str] = set()

    def add(ident: str) -> None:
        if ident in seen or ident not in nodes:
            return
        seen.add(ident)
        keep.append(ident)

    for ident in sorted(priority):
        add(ident)
        if len(keep) >= node_limit:
            break
    if len(keep) < node_limit:
        for ident in sorted(connected, key=lambda i: (-len(adj.get(i, ())), i)):
            add(ident)
            if len(keep) >= node_limit:
                break
    rest = sorted(
        (i for i in nodes if i not in seen),
        key=lambda i: (-len(adj.get(i, ())), str(nodes[i].get("type") or ""), i),
    )
    for ident in rest:
        if len(keep) >= node_limit:
            break
        add(ident)
    keep_set = set(keep[:node_limit])
    out_nodes = {k: nodes[k] for k in keep if k in keep_set}
    ranked_edges = sorted(
        (e for e in edges if e["source"] in out_nodes and e["target"] in out_nodes),
        key=lambda e: (
            0 if nodes.get(e["source"], {}).get("type") in PRIORITY_TYPES
            or nodes.get(e["target"], {}).get("type") in PRIORITY_TYPES else 1,
            e["type"], e["source"], e["target"],
        ),
    )
    out_edges = ranked_edges[:edge_limit]
    truncated = len(nodes) > len(out_nodes) or len(edges) > len(out_edges)
    return out_nodes, out_edges, truncated


def _resolve_wiki(link: str, by_path: dict[str, str], by_stem: dict[str, str], by_title: dict[str, str]) -> str | None:
    text = (link or "").replace("\\", "/").strip().lstrip("/")
    if not text:
        return None
    key = text.casefold()
    if key in by_path:
        return by_path[key]
    if not key.endswith(".md") and (key + ".md") in by_path:
        return by_path[key + ".md"]
    stem = text.rsplit("/", 1)[-1]
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    if stem.casefold() in by_stem:
        return by_stem[stem.casefold()]
    if text.casefold() in by_title:
        return by_title[text.casefold()]
    return None
