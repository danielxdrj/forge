"""Issues concluídas semelhantes: palavras-chave + mesmo repo. Sem embeddings.

Notas do vault Obsidian ficam de fora do prompt e deste ranking.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..graphs import store as graph_store
from ..storage.sql import SqlRepository
from .store import CompletedIssue, list_all

TOP_N = 5
STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "not", "but", "you", "your", "have", "has", "had", "into", "over",
    "uma", "uns", "uma", "para", "com", "que", "nao", "não", "dos", "das",
    "pelo", "pela", "sem", "como", "mais", "menos", "este", "esta", "isso",
    "uma", "fix", "feat", "chore", "docs", "test", "refactor",
})
TOKEN = re.compile(r"[a-z0-9_]{3,}")
PROMPT_BODY = 1500


def tokenize(text: str) -> set[str]:
    return {t for t in TOKEN.findall((text or "").casefold()) if t not in STOP}


def find_related(
    repo: SqlRepository,
    query: str,
    current_repo: str,
    *,
    exclude: tuple[str, int] | None = None,
    graph_dir: str | Path | None = None,
    limit: int = TOP_N,
) -> list[dict]:
    """Devolve até `limit` issues, com nós Graphify dos arquivos dos PRs ligados."""
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    current = (current_repo or "").strip().lower()
    scored: list[tuple[int, CompletedIssue]] = []
    for item in list_all(repo):
        if exclude and item.repo.lower() == exclude[0].lower() and item.number == exclude[1]:
            continue
        hay = tokenize(item.title) | tokenize(item.body)
        names = item.labels.get("names") if isinstance(item.labels, dict) else []
        hay |= tokenize(" ".join(str(n) for n in (names or [])))
        overlap = len(q_tokens & hay)
        if overlap <= 0:
            continue
        score = overlap
        if item.repo.lower() == current:
            score += 2
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].repo, -pair[1].number))
    out = []
    root = Path(graph_dir) if graph_dir else None
    for score, item in scored[: max(1, min(int(limit), 20))]:
        files = _files_of(item)
        nodes = graph_store.nodes_for_files(root, item.repo, files) if root is not None else []
        payload = item.as_json(include_body=False)
        payload["score"] = score
        payload["files"] = files
        payload["nodes"] = nodes
        payload["body_excerpt"] = (item.body or "")[:PROMPT_BODY]
        out.append(payload)
    return out


def format_related_prompt(related: list[dict]) -> str:
    """Texto para o LLM. Corpos já redigidos na importação. Sem notas do vault."""
    if not related:
        return ""
    lines = [
        "ISSUES_CONCLUIDAS_RELACIONADAS (já públicas no GitHub; use como contexto, não copie segredos):",
    ]
    for item in related:
        key = f"{item.get('repo')}#{item.get('number')}"
        lines.append(f"- {key} {item.get('title') or ''}".rstrip())
        url = item.get("url") or ""
        if url:
            lines.append(f"  url: {url}")
        excerpt = (item.get("body_excerpt") or "").strip()
        if excerpt:
            lines.append("  corpo: " + " ".join(excerpt.split())[:PROMPT_BODY])
        files = item.get("files") or []
        if files:
            lines.append("  arquivos: " + ", ".join(files[:20]))
        nodes = item.get("nodes") or []
        if nodes:
            bits = []
            for node in nodes[:8]:
                label = node.get("label") or node.get("id") or ""
                path = node.get("file") or ""
                bits.append(f"{label} ({path})" if path else label)
            if bits:
                lines.append("  grafo: " + "; ".join(bits))
    return "\n".join(lines)


def format_related_section(related: list[dict]) -> str:
    if not related:
        return ""
    lines = ["## Issues relacionadas", ""]
    for item in related:
        repo = item.get("repo") or ""
        number = item.get("number")
        title = item.get("title") or ""
        url = item.get("url") or ""
        label = f"{repo}#{number}"
        if url:
            lines.append(f"- [{label}]({url}) — {title}".rstrip(" —"))
        else:
            lines.append(f"- {label} — {title}".rstrip(" —"))
        for pr in item.get("prs") or []:
            if not isinstance(pr, dict):
                continue
            pr_url = pr.get("url") or ""
            pr_n = pr.get("number")
            files = ", ".join(f"`{p}`" for p in (pr.get("files") or [])[:12] if p)
            pr_label = f"PR #{pr_n}"
            if pr_url:
                lines.append(f"  - [{pr_label}]({pr_url})" + (f": {files}" if files else ""))
            elif files:
                lines.append(f"  - {pr_label}: {files}")
        nodes = item.get("nodes") or []
        if nodes:
            bits = []
            for node in nodes[:8]:
                name = node.get("label") or node.get("id") or ""
                path = node.get("file") or ""
                if name and path:
                    bits.append(f"`{name}` (`{path}`)")
                elif name:
                    bits.append(f"`{name}`")
            if bits:
                lines.append("  - Grafo: " + ", ".join(bits))
    return "\n".join(lines).rstrip() + "\n"


def _files_of(item: CompletedIssue) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for pr in item.prs or []:
        if not isinstance(pr, dict):
            continue
        for path in pr.get("files") or []:
            text = str(path).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


