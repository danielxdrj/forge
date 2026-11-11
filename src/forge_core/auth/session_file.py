"""Arquivo local da sessão CLI (volume forge_cli_home). Só o token de sessão do Forge; sem token GitHub."""
from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

from ..errors import ConfigError

_REL = Path("forge") / "session"


def session_file_path(env: Mapping[str, str]) -> Path:
    override = (env.get("FORGE_SESSION_FILE") or "").strip()
    if override:
        return Path(override)
    xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg:
        return Path(xdg) / _REL
    home = (env.get("HOME") or "").strip()
    if home:
        return Path(home) / ".config" / _REL
    raise ConfigError("HOME, XDG_CONFIG_HOME ou FORGE_SESSION_FILE é obrigatório para a sessão CLI")


def read_session_token(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    token = text.strip()
    return token or None


def write_session_token(path: Path, token: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    os.chmod(path, 0o600)


def delete_session_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def session_file_mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None
