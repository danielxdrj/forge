"""Nota Obsidian de uma issue concluída: `Forge/<repo>/<number>.md`. Sem symlink."""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings
from ..obsidian.vault import VaultRuleError
from ..obsidian.write import prepare_write
from .store import CompletedIssue

log = logging.getLogger("forge_core.issues")


def render_note(item: CompletedIssue) -> str:
    labels = item.labels if isinstance(item.labels, dict) else {}
    names = [str(n) for n in (labels.get("names") or []) if str(n).strip()]
    for key in ("tipo", "prioridade", "sprint"):
        value = str(labels.get(key) or "").strip()
        if value and value not in names:
            names.append(value)
    pr_numbers = []
    for pr in item.prs or []:
        if isinstance(pr, dict) and pr.get("number") is not None:
            pr_numbers.append(int(pr["number"]))
    fm = ["---", f"repo: {item.repo}", f"number: {item.number}"]
    if names:
        fm.append("labels:")
        for name in names:
            fm.append(f"  - {name}")
    else:
        fm.append("labels: []")
    if item.closed_at:
        fm.append(f"closed_at: {item.closed_at}")
    if pr_numbers:
        fm.append("prs: [" + ", ".join(str(n) for n in pr_numbers) + "]")
    else:
        fm.append("prs: []")
    fm.append("---")
    lines = fm + ["", f"# {item.title}".rstrip(), ""]
    if item.url:
        lines.append(f"- [Issue]({item.url})")
    for pr in item.prs or []:
        if not isinstance(pr, dict):
            continue
        pr_url = pr.get("url") or ""
        pr_n = pr.get("number")
        if pr_url:
            lines.append(f"- [PR #{pr_n}]({pr_url})")
        for path in pr.get("files") or []:
            href = _file_url(item.repo, str(path))
            if href:
                lines.append(f"  - [`{path}`]({href})")
            else:
                lines.append(f"  - `{path}`")
    body = (item.body or "").strip()
    if body:
        lines.extend(["", "## Corpo", "", body])
    return "\n".join(lines).rstrip() + "\n"


def write_issue_note(settings: Settings, item: CompletedIssue) -> str | None:
    """Grava a nota se o vault e `Forge/` existirem. Sem vault, não faz nada."""
    raw = (settings.obsidian_vault or "").strip()
    if not raw:
        return None
    root = Path(raw)
    if not root.is_dir():
        return None
    repo_name = item.repo.split("/")[-1]
    relative = f"{repo_name}/{item.number}.md"
    try:
        dest = prepare_write(root, relative, render_note(item).encode("utf-8"))
    except VaultRuleError as exc:
        log.info("issues.note repo=%s number=%s result=error:%s", item.repo, item.number, exc.code)
        return None
    log.info("issues.note repo=%s number=%s path=%s bytes=%s", item.repo, item.number, relative, dest.stat().st_size)
    return relative


def _file_url(repo: str, path: str) -> str:
    clean = (path or "").replace("\\", "/").lstrip("/")
    if not clean or ".." in clean.split("/"):
        return ""
    return f"https://github.com/{repo}/blob/HEAD/{clean}"
