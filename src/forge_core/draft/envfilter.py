"""Allowlist de ambiente para subprocessos. Nunca copia o ambiente do host inteiro."""
from __future__ import annotations

from collections.abc import Mapping

# Login nativo da Cursor CLI (loja dela) e PATH. Sem FORGE_*, banco, GitHub.
CURSOR_ENV_ALLOW = frozenset({
    "PATH", "PATHEXT", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
    "CURSOR_API_KEY", "CURSOR_AUTH_TOKEN",
    "LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT", "WINDIR", "COMSPEC",
    "PROGRAMFILES", "PROGRAMFILES(X86)",
})

# Keyring nativo do gh. GH_TOKEN/GITHUB_TOKEN ficam de fora de propósito.
GH_ENV_ALLOW = frozenset({
    "PATH", "PATHEXT", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "GH_HOST",
    "LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT", "WINDIR", "COMSPEC",
})

_BLOCK_PREFIX = ("FORGE_", "POSTGRES_", "PG", "AWS_", "SSH_")
_BLOCK_EXACT = frozenset({
    "GH_TOKEN", "GITHUB_TOKEN", "DATABASE_URL", "FORGE_DATABASE_URL",
    "FORGE_DATABASE_MIGRATION_URL", "CURSOR_API_KEY", "CURSOR_AUTH_TOKEN",
})


def filter_env(src: Mapping[str, str], allow: frozenset[str], *,
               extra_allow: frozenset[str] | None = None) -> dict[str, str]:
    """Copia só chaves permitidas. Bloqueia tokens GitHub/Forge mesmo se listados por engano."""
    allowed = set(allow)
    if extra_allow:
        allowed |= extra_allow
    out: dict[str, str] = {}
    for key, value in src.items():
        if key in _BLOCK_EXACT and key not in allow:
            continue
        if key.startswith("FORGE_") or key.startswith("POSTGRES_"):
            continue
        if key in ("GH_TOKEN", "GITHUB_TOKEN", "DATABASE_URL"):
            continue
        if key in allowed:
            out[key] = value
    return out


def assert_no_host_secrets(env: Mapping[str, str]) -> None:
    for key in env:
        if key in ("GH_TOKEN", "GITHUB_TOKEN", "DATABASE_URL") or key.startswith("FORGE_"):
            raise AssertionError(f"env vazou {key}")
