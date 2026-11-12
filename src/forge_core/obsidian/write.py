"""Escrita atômica só em `Forge/`. Caminho final: realpath, sem symlink, nome sanitizado.

Aceita arquivo na raiz de Forge/ (`nota.md`) ou um nível de pasta (`site/34.md`).
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .vault import VaultRuleError, _has_symlink_in_parents, _inside

FORGE_FOLDER = "Forge"
SAFE_REL = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}(?:/[A-Za-z0-9][A-Za-z0-9._-]{0,80}){0,4}\.md$"
)


def prepare_write(vault_root: Path, name: str, content: bytes) -> Path:
    """Grava `name` em `<vault>/Forge/` de forma atômica. Devolve o caminho final.

    Recusa `..`, symlink e destino fora de Forge/. Cria pastas intermediárias só sob Forge/.
    """
    rel = (name or "").replace("\\", "/").strip().lstrip("/")
    if not SAFE_REL.fullmatch(rel) or ".." in rel.split("/"):
        raise VaultRuleError("invalid_name")
    if not isinstance(content, (bytes, bytearray)):
        raise VaultRuleError("invalid_body")
    root = vault_root.resolve()
    forge = (root / FORGE_FOLDER).resolve()
    if not _inside(root, forge):
        raise VaultRuleError("path_forbidden")
    if forge.is_symlink() or _has_symlink_in_parents(root, forge):
        raise VaultRuleError("path_forbidden")
    if not forge.is_dir():
        raise VaultRuleError("forge_missing")
    dest = (forge / rel).resolve()
    if not _inside(forge, dest):
        raise VaultRuleError("path_forbidden")
    parent = dest.parent
    _ensure_dir(root, forge, parent)
    if dest.exists() and (dest.is_symlink() or dest.is_dir()):
        raise VaultRuleError("path_forbidden")
    fd, tmp_name = tempfile.mkstemp(prefix=".forge-", suffix=".tmp", dir=str(parent))
    tmp_path = Path(tmp_name)
    try:
        if tmp_path.is_symlink() or not _inside(forge, tmp_path.resolve()):
            raise VaultRuleError("path_forbidden")
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, dest)
    except VaultRuleError:
        _unlink(tmp_path)
        raise
    except OSError as exc:
        _unlink(tmp_path)
        raise VaultRuleError("write_failed") from exc
    final = dest.resolve()
    if not _inside(forge, final) or final.is_symlink():
        _unlink(final)
        raise VaultRuleError("write_failed")
    return final


def _ensure_dir(root: Path, forge: Path, directory: Path) -> None:
    if directory == forge:
        if directory.is_symlink() or _has_symlink_in_parents(root, directory):
            raise VaultRuleError("path_forbidden")
        return
    if not _inside(forge, directory):
        raise VaultRuleError("path_forbidden")
    _ensure_dir(root, forge, directory.parent)
    if directory.exists():
        if directory.is_symlink() or not directory.is_dir():
            raise VaultRuleError("path_forbidden")
        if _has_symlink_in_parents(root, directory):
            raise VaultRuleError("path_forbidden")
        return
    try:
        directory.mkdir(mode=0o755)
    except OSError as exc:
        raise VaultRuleError("write_failed") from exc
    resolved = directory.resolve()
    if directory.is_symlink() or not _inside(forge, resolved) or _has_symlink_in_parents(root, resolved):
        try:
            directory.rmdir()
        except OSError:
            pass
        raise VaultRuleError("path_forbidden")


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
