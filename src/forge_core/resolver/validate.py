"""Validação do diff produzido no clone temporário (ADR-016)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..errors import DraftError

MAX_FILES = 30
MAX_LINES = 4000
SENSITIVE = re.compile(
    r"(^|/)\.env($|\.)|(^|/)id_rsa|(^|/).*?\.pem$|(^|/)credentials|(^|/).*?\.key$"
    r"|(^|/)secrets|(^|/)\.git/config|(^|/)\.git/hooks/",
    re.IGNORECASE,
)
BLOCKED_NAMES = frozenset({".gitattributes", ".gitmodules"})
DIFF_FILE = re.compile(r"^(?:---|\+\+\+) [ab]/(.+)$")
DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")
_SKIP_GIT = frozenset({"objects", "refs", "logs", "packed-refs", "HEAD", "index", "COMMIT_EDITMSG"})


def snapshot_git_meta(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    git = root / ".git"
    if not git.is_dir():
        return out
    hooks = git / "hooks"
    if hooks.is_dir():
        names = sorted(p.name for p in hooks.iterdir())
        out["hooks/:names"] = "\n".join(names)
        for path in sorted(hooks.iterdir()):
            if path.is_file() or path.is_symlink():
                rel = f"hooks/{path.name}"
                out[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "symlink"
    for path in git.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(git)).replace("\\", "/")
        top = rel.split("/", 1)[0]
        if top in _SKIP_GIT or rel.startswith("objects/") or rel.startswith("refs/") or rel.startswith("logs/"):
            continue
        if top in ("config", "hooks", "info") or "config" in path.name.lower():
            if rel.startswith("hooks/"):
                continue
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def assert_git_meta_unchanged(root: Path, before: dict[str, str]) -> None:
    after = snapshot_git_meta(root)
    if after != before:
        raise DraftError("git_meta_tampered")


def parse_changed_files(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        match = DIFF_PATH.match(line)
        if match:
            files.append(match.group(2))
            continue
        match = DIFF_FILE.match(line)
        if match and match.group(1) != "/dev/null":
            files.append(match.group(1))
    seen = []
    for name in files:
        if name not in seen:
            seen.append(name)
    return seen


def validate_diff(diff: str, clone: Path) -> dict:
    if not (diff or "").strip():
        raise DraftError("empty_diff")
    files = parse_changed_files(diff)
    if not files:
        files = ["(working-tree)"]
    if len(files) > MAX_FILES:
        raise DraftError("diff_too_large", "files")
    added = sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    if added + removed > MAX_LINES:
        raise DraftError("diff_too_large", "lines")
    root = clone.resolve()
    for rel in files:
        if rel == "(working-tree)":
            continue
        name = Path(rel).name
        if name in BLOCKED_NAMES:
            raise DraftError("sensitive_diff", rel)
        if rel.startswith("/") or rel.startswith("\\") or ".." in Path(rel).parts:
            raise DraftError("diff_outside_clone")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise DraftError("diff_outside_clone") from exc
        if SENSITIVE.search(rel.replace("\\", "/")):
            raise DraftError("sensitive_diff", rel)
        if ".cursor/" in rel.replace("\\", "/") or rel.replace("\\", "/").startswith(".cursor"):
            raise DraftError("sensitive_diff", rel)
    digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    return {"files": files, "lines": added + removed, "hash": digest, "stat": f"{len(files)} files, {added + removed} lines"}
