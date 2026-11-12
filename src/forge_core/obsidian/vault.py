"""Listar e ler `.md` só nas pastas da allowlist. Sem symlink, sem sair do vault.

O conteúdo nunca vai para o log: só caminho relativo e hash. Sem vault ou sem
allowlist, a área fica desligada (`enabled=False`).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..errors import ForgeError

log = logging.getLogger("forge_core.obsidian")

MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 200
WIKI_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TAG = re.compile(r"(?<!\w)#([A-Za-z0-9][A-Za-z0-9_/-]{0,63})")
SAFE_REL = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.md$")


class VaultRuleError(ForgeError):
    """Falha de leitura do vault. Código fixo; sem conteúdo da nota."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class VaultNoteMeta:
    path: str
    title: str
    tags: tuple[str, ...]
    links: tuple[str, ...]
    bytes: int
    sha256: str

    def as_json(self) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "tags": list(self.tags),
            "links": list(self.links),
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


class ObsidianVault:
    def __init__(
        self,
        root: Path | None,
        allow: tuple[str, ...],
        *,
        reason: str = "vault_disabled",
        max_file_bytes: int = MAX_FILE_BYTES,
        max_files: int = MAX_FILES,
    ):
        self._root = root
        self._allow = allow
        self.reason = reason
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    @property
    def enabled(self) -> bool:
        return self._root is not None and bool(self._allow)

    def status(self) -> dict:
        if not self.enabled:
            return {
                "enabled": False,
                "error": self.reason,
                "message": "Vault Obsidian desligado: defina FORGE_OBSIDIAN_VAULT "
                "(caminho absoluto no container) e FORGE_OBSIDIAN_ALLOW "
                "(pastas relativas, separadas por vírgula).",
            }
        return {"enabled": True, "allow": list(self._allow)}

    @classmethod
    def disabled(cls, reason: str = "vault_disabled") -> "ObsidianVault":
        return cls(None, (), reason=reason)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ObsidianVault":
        raw = (settings.obsidian_vault or "").strip()
        allow = tuple(settings.obsidian_allow)
        if not raw or not allow:
            return cls.disabled("vault_disabled")
        try:
            root = Path(raw)
            if not root.exists() or not root.is_dir():
                return cls.disabled("vault_disabled")
            resolved = root.resolve(strict=True)
        except (OSError, RuntimeError):
            return cls.disabled("vault_disabled")
        if resolved.is_symlink():
            return cls.disabled("vault_disabled")
        return cls(resolved, allow)

    def list_notes(self) -> dict:
        self._need()
        notes: list[VaultNoteMeta] = []
        truncated = False
        for folder in self._allow:
            base = self._allowed_dir(folder)
            if base is None:
                continue
            for path in _walk_md(base):
                if len(notes) >= self.max_files:
                    truncated = True
                    break
                meta = self._meta_of(path)
                if meta is not None:
                    notes.append(meta)
            if truncated:
                break
        notes.sort(key=lambda n: n.path)
        return {"enabled": True, "truncated": truncated, "notes": [n.as_json() for n in notes]}

    def read_note(self, relative: str) -> dict:
        self._need()
        path = self._resolve_readable(relative)
        data = _read_capped(path, self.max_file_bytes)
        digest = hashlib.sha256(data).hexdigest()
        text = data.decode("utf-8", "replace")
        rel = self._rel(path)
        log.info("vault.read path=%s hash=%s bytes=%s", rel, digest[:16], len(data))
        meta = _parse_markdown(text, rel, len(data), digest)
        payload = meta.as_json()
        payload["body"] = text
        return payload

    def _need(self) -> None:
        if not self.enabled:
            raise VaultRuleError(self.reason)

    def _allowed_dir(self, folder: str) -> Path | None:
        assert self._root is not None
        candidate = (self._root / folder).resolve()
        if not _inside(self._root, candidate):
            return None
        if not candidate.is_dir() or candidate.is_symlink():
            return None
        if _has_symlink_in_parents(self._root, candidate):
            return None
        return candidate

    def _resolve_readable(self, relative: str) -> Path:
        rel = _clean_relative(relative)
        assert self._root is not None
        candidate = self._root / rel
        if candidate.is_symlink() or _has_symlink_in_parents(self._root, candidate):
            raise VaultRuleError("path_forbidden")
        raw = candidate.resolve()
        if not _inside(self._root, raw):
            raise VaultRuleError("path_forbidden")
        if not any(_inside(base, raw) for base in self._allowed_bases()):
            raise VaultRuleError("path_forbidden")
        if raw.is_symlink() or _has_symlink_in_parents(self._root, raw):
            raise VaultRuleError("path_forbidden")
        if not raw.is_file():
            raise VaultRuleError("not_found")
        try:
            size = raw.stat().st_size
        except OSError as exc:
            raise VaultRuleError("not_found") from exc
        if size > self.max_file_bytes:
            raise VaultRuleError("file_too_large")
        return raw

    def _allowed_bases(self) -> list[Path]:
        out = []
        for folder in self._allow:
            base = self._allowed_dir(folder)
            if base is not None:
                out.append(base)
        return out

    def _rel(self, path: Path) -> str:
        assert self._root is not None
        return path.relative_to(self._root).as_posix()

    def _meta_of(self, path: Path) -> VaultNoteMeta | None:
        try:
            if path.is_symlink() or not path.is_file():
                return None
            size = path.stat().st_size
            if size > self.max_file_bytes:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        if len(data) > self.max_file_bytes:
            return None
        digest = hashlib.sha256(data).hexdigest()
        rel = self._rel(path)
        log.info("vault.list path=%s hash=%s bytes=%s", rel, digest[:16], len(data))
        return _parse_markdown(data.decode("utf-8", "replace"), rel, len(data), digest)


def _clean_relative(relative: str) -> str:
    text = (relative or "").replace("\\", "/").strip().lstrip("/")
    if not SAFE_REL.fullmatch(text):
        raise VaultRuleError("path_forbidden")
    bits = text.split("/")
    if ".." in bits or any(b in ("", ".") for b in bits[:-1]):
        raise VaultRuleError("path_forbidden")
    return text


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _has_symlink_in_parents(root: Path, target: Path) -> bool:
    try:
        current = target
        while True:
            if current.is_symlink():
                return True
            if current == root:
                break
            parent = current.parent
            if parent == current:
                break
            current = parent
    except OSError:
        return True
    return False


def _walk_md(base: Path):
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        current = Path(dirpath)
        if current.is_symlink():
            dirnames[:] = []
            continue
        dirnames[:] = [
            name for name in dirnames
            if not (current / name).is_symlink() and not name.startswith(".")
        ]
        for name in filenames:
            if not name.endswith(".md") or name.startswith("."):
                continue
            path = current / name
            if path.is_symlink():
                continue
            yield path


def _read_capped(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as fh:
            data = fh.read(limit + 1)
    except OSError as exc:
        raise VaultRuleError("not_found") from exc
    if len(data) > limit:
        raise VaultRuleError("file_too_large")
    return data


def _parse_markdown(text: str, rel: str, size: int, digest: str) -> VaultNoteMeta:
    fm, body = _split_frontmatter(text)
    title = str(fm.get("title") or "").strip() or Path(rel).stem.replace("-", " ")
    tags = _tags(fm, body)
    links = tuple(dict.fromkeys(m.strip() for m in WIKI_LINK.findall(text) if m.strip()))
    return VaultNoteMeta(rel, title, tags, links, size, digest)


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    raw = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    return _simple_yaml(raw), body


def _simple_yaml(raw: str) -> dict[str, object]:
    data: dict[str, object] = {}
    current_list: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list:
            items = data.setdefault(current_list, [])
            if isinstance(items, list):
                items.append(stripped[2:].strip().strip("'\""))
            continue
        if ":" not in line:
            current_list = None
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if not key:
            continue
        current_list = None
        if rest == "":
            data[key] = []
            current_list = key
            continue
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            data[key] = [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
            continue
        data[key] = rest.strip("'\"" )
    return data


def _tags(fm: dict[str, object], body: str) -> tuple[str, ...]:
    found: list[str] = []
    raw = fm.get("tags") or fm.get("tag")
    if isinstance(raw, str):
        found.extend(p.strip() for p in raw.replace(",", " ").split() if p.strip())
    elif isinstance(raw, list):
        found.extend(str(p).strip() for p in raw if str(p).strip())
    found.extend(TAG.findall(body))
    out: list[str] = []
    seen: set[str] = set()
    for tag in found:
        tag = tag.lstrip("#")
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return tuple(out)
