"""Escrita atômica só em `Forge/`. Usado na fase 2; a fase 1 só expõe o helper.

Caminho final passa por realpath, bloqueia symlink e sanitiza o nome do arquivo.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .vault import VaultRuleError, _has_symlink_in_parents, _inside

FORGE_FOLDER = "Forge"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.md$")


def prepare_write(vault_root: Path, name: str, content: bytes) -> Path:
    """Grava `name` em `<vault>/Forge/` de forma atômica. Devolve o caminho final.

    Recusa nome com barra, `..`, symlink e destino fora de Forge/.
    """
    if not SAFE_NAME.fullmatch(name or ""):
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
    dest = (forge / name).resolve()
    if not _inside(forge, dest):
        raise VaultRuleError("path_forbidden")
    if dest.exists() and (dest.is_symlink() or dest.is_dir()):
        raise VaultRuleError("path_forbidden")
    fd, tmp_name = tempfile.mkstemp(prefix=".forge-", suffix=".tmp", dir=str(forge))
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
        raise VaultRuleError("path_forbidden")
    return final


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
