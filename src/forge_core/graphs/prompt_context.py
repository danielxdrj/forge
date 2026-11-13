"""Seção "## Contexto do grafo" para prompts do motor (economia de tokens).

Lê só os grafos Graphify já indexados (graph.json por repositório, sob `graph_dir`).
Nunca toca notas do vault Obsidian nem a tabela de issues/notas: o conteúdo vem
exclusivamente do código indexado. Por segurança (defesa em profundidade), o texto
final ainda passa por `redaction.redact_secrets` antes de voltar ao chamador.

Sem grafo indexado para nenhum repositório informado, devolve string vazia, em silêncio.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from ..redaction import redact_secrets
from . import store

DEFAULT_MAX_NODES = 40
DEFAULT_MAX_CHARS = 6000
_TOKEN = re.compile(r"[a-z0-9_]{3,}")
HEADER = "## Contexto do grafo"


def _tokenize(text: str) -> set[str]:
    """Tokens de 3+ chars; identificadores com `_` também contam pelas partes (snake_case)."""
    out: set[str] = set()
    for tok in _TOKEN.findall((text or "").casefold()):
        out.add(tok)
        if "_" in tok:
            out.update(part for part in tok.split("_") if len(part) >= 3)
    return out


def _node_text(node: dict) -> str:
    bits = [
        str(node.get("label") or node.get("name") or ""),
        str(node.get("id") or ""),
        str(node.get("file") or node.get("path") or node.get("source_file") or ""),
    ]
    return " ".join(bits)


def _endpoint(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        return str(raw.get("id") or raw.get("label") or "")
    return str(raw)


def _node_path(node: dict) -> str:
    return str(node.get("file") or node.get("path") or node.get("source_file") or "").replace("\\", "/")


def _node_label(node: dict) -> str:
    return str(node.get("label") or node.get("name") or node.get("id") or "")


def _node_kind(node: dict) -> str:
    return str(node.get("kind") or node.get("type") or "code")


def _relevant_nodes(nodes: list, edges: list, query_tokens: set[str], budget: int) -> list[dict]:
    """Nós cujo texto compartilha token com a consulta, mais vizinhos de 1º grau, até `budget`."""
    by_id: dict[str, dict] = {}
    for node in nodes:
        if isinstance(node, dict) and node.get("id") is not None:
            by_id[str(node["id"])] = node
    if not by_id:
        return []
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src = _endpoint(edge.get("source") or edge.get("from"))
        dst = _endpoint(edge.get("target") or edge.get("to"))
        if src in by_id and dst in by_id and src != dst:
            adjacency.setdefault(src, set()).add(dst)
            adjacency.setdefault(dst, set()).add(src)
    scored: list[tuple[int, str]] = []
    for ident, node in by_id.items():
        overlap = len(_tokenize(_node_text(node)) & query_tokens)
        if overlap > 0:
            scored.append((overlap, ident))
    if not scored:
        return []
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    primary_cap = max(1, budget // 2) if budget else len(scored)
    primary = [ident for _score, ident in scored[:primary_cap]]
    chosen: list[str] = []
    seen: set[str] = set()
    for ident in primary:
        if ident in seen:
            continue
        seen.add(ident)
        chosen.append(ident)
        if budget and len(chosen) >= budget:
            break
    if not budget or len(chosen) < budget:
        neighbor_ids: list[str] = []
        for ident in primary:
            for neighbor in sorted(adjacency.get(ident, ())):
                if neighbor not in seen:
                    neighbor_ids.append(neighbor)
        for ident in neighbor_ids:
            if ident in seen:
                continue
            seen.add(ident)
            chosen.append(ident)
            if budget and len(chosen) >= budget:
                break
    out = []
    for ident in chosen:
        node = dict(by_id[ident])
        node["_neighbors"] = sorted(
            _node_label(by_id[n]) or n for n in adjacency.get(ident, ()) if n in seen
        )[:6]
        out.append(node)
    return out


def _format_section(repo: str, nodes: list[dict]) -> list[str]:
    lines: list[str] = []
    for node in nodes:
        label = _node_label(node)
        path = _node_path(node)
        kind = _node_kind(node)
        head = f"- `{label}`" if label else "- (sem nome)"
        if path and path != label:
            head += f" (`{path}`)"
        head += f" — tipo: {kind}, repo: {repo}"
        lines.append(head)
        neighbors = node.get("_neighbors") or []
        if neighbors:
            lines.append("  - vizinhos: " + ", ".join(str(n) for n in neighbors))
    return lines


def graph_prompt_section(
    graph_dir: str | Path | None,
    text: str,
    repos: Sequence[str],
    *,
    max_nodes: int | None = None,
    max_chars: int | None = None,
) -> str:
    """Seção Markdown enxuta de contexto do grafo para injetar num prompt.

    `graph_dir` é o diretório raiz dos grafos indexados (`Settings.graph_dir`).
    Sem grafo (diretório ausente, repositório não indexado, ou sem nó relevante),
    devolve "" em silêncio: a ausência de contexto do grafo nunca é um erro.
    """
    if not graph_dir or not repos:
        return ""
    query_tokens = _tokenize(text)
    if not query_tokens:
        return ""
    node_budget = max_nodes if max_nodes and max_nodes > 0 else DEFAULT_MAX_NODES
    char_budget = max_chars if max_chars and max_chars > 0 else DEFAULT_MAX_CHARS
    root = Path(graph_dir)
    lines: list[str] = [HEADER]
    remaining_nodes = node_budget
    any_repo = False
    for full_repo in repos:
        if remaining_nodes <= 0:
            break
        data = store.load_graph(root, full_repo)
        if data is None:
            continue
        nodes, edges = store.nodes_edges(data)
        picked = _relevant_nodes(nodes, edges, query_tokens, remaining_nodes)
        if not picked:
            continue
        any_repo = True
        lines.extend(_format_section(full_repo, picked))
        remaining_nodes -= len(picked)
    if not any_repo:
        return ""
    section = "\n".join(lines).strip() + "\n"
    section = redact_secrets(section)
    encoded = section.encode("utf-8")
    if len(encoded) > char_budget:
        section = encoded[:char_budget].decode("utf-8", "ignore").rstrip() + "\n[truncado]\n"
    return section
