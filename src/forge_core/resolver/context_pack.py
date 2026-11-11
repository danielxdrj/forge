"""Pacote de contexto com teto de tamanho: issue, árvore, docs/, README e arquivos citados."""
from __future__ import annotations

import re
from pathlib import Path

from ..errors import DraftError
from ..logging import redact

MAX_PACK_BYTES = 96 * 1024
CITED = re.compile(r"(?:^|[\s`'(])([\w./\\-]+\.(?:py|md|ts|tsx|js|jsx|toml|yml|yaml|json|sql|txt|rst))")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".cursor"}


def comments_text(payload: dict) -> str:
    comments = payload.get("comments") or []
    if isinstance(comments, dict):
        comments = comments.get("nodes") or comments.get("items") or []
    if not isinstance(comments, list):
        return ""
    parts = []
    for item in comments:
        if isinstance(item, dict):
            body = item.get("body") or item.get("text") or ""
            author = ""
            user = item.get("author") or item.get("user") or {}
            if isinstance(user, dict):
                author = str(user.get("login") or "")
            elif isinstance(user, str):
                author = user
            parts.append(f"{author}: {body}".strip())
        elif isinstance(item, str):
            parts.append(item)
    return "\n\n".join(parts)


def cited_paths(text: str) -> list[str]:
    found = []
    for match in CITED.finditer(text or ""):
        path = match.group(1).replace("\\", "/")
        if path not in found and ".." not in path.split("/"):
            found.append(path)
    return found


def tree_listing(root: Path, files: list[str], limit: int = 200) -> str:
    names = files[:limit] if files else []
    if not names:
        names = []
        for path in sorted(root.rglob("*")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                names.append(str(path.relative_to(root)).replace("\\", "/"))
            if len(names) >= limit:
                break
    return "\n".join(names)


def _read_capped(path: Path, remaining: int) -> str:
    if remaining <= 0 or not path.is_file():
        return ""
    raw = path.read_bytes()
    if b"\x00" in raw:
        return ""
    text = raw.decode("utf-8", "replace")
    text = redact(text)
    encoded = text.encode("utf-8")
    if len(encoded) > remaining:
        return encoded[:remaining].decode("utf-8", "ignore") + "\n[truncado]\n"
    return text


def build_pack(*, issue: dict, root: Path, tracked: list[str] | None = None) -> str:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    comments = comments_text(issue)
    issue_block = f"# ISSUE\n{title}\n\n{body}\n\n# COMENTARIOS\n{comments}\n"
    cited = cited_paths(title + "\n" + body + "\n" + comments)
    tree = tree_listing(root, tracked or [])
    parts = [issue_block, "# ARVORE\n" + tree + "\n"]
    budget = MAX_PACK_BYTES - len("".join(parts).encode("utf-8"))
    for rel in ("README.md", "README.rst", "README.txt"):
        chunk = _read_capped(root / rel, max(0, budget))
        if chunk:
            parts.append(f"# {rel}\n{chunk}\n")
            budget = MAX_PACK_BYTES - len("".join(parts).encode("utf-8"))
    docs = root / "docs"
    if docs.is_dir() and budget > 0:
        for path in sorted(docs.rglob("*")):
            if not path.is_file() or any(p in SKIP_DIRS for p in path.parts):
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            chunk = _read_capped(path, max(0, budget))
            if not chunk:
                continue
            parts.append(f"# {rel}\n{chunk}\n")
            budget = MAX_PACK_BYTES - len("".join(parts).encode("utf-8"))
            if budget <= 0:
                break
    for rel in cited:
        if budget <= 0:
            break
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        chunk = _read_capped(path, max(0, budget))
        if chunk:
            parts.append(f"# citado:{rel}\n{chunk}\n")
            budget = MAX_PACK_BYTES - len("".join(parts).encode("utf-8"))
    pack = "".join(parts)
    encoded = pack.encode("utf-8")
    if len(encoded) > MAX_PACK_BYTES:
        pack = encoded[:MAX_PACK_BYTES].decode("utf-8", "ignore") + "\n[truncado]\n"
    if "GH_TOKEN" in pack or "FORGE_DATABASE" in pack:
        raise DraftError("secret_in_prompt")
    return pack
