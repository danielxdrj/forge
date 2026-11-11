"""Allowlist de ambiente para subprocessos. Nunca copia o ambiente do host inteiro."""
from __future__ import annotations

from collections.abc import Mapping

# Autenticação/caminhos da Cursor CLI (código 2026.11.10: CURSOR_API_KEY, CURSOR_AUTH_TOKEN,
# CURSOR_CONFIG_DIR, CURSOR_DATA_DIR, CURSOR_API_ENDPOINT). Não copiar CURSOR_* genérico
# (há CURSOR_ASKPASS_SECRET, CURSOR_LOCAL_AGENT_HEADERS, etc.).
CURSOR_AUTH_ALLOW = frozenset({
    "CURSOR_API_KEY", "CURSOR_AUTH_TOKEN", "CURSOR_CONFIG_DIR", "CURSOR_DATA_DIR",
    "CURSOR_API_ENDPOINT",
})

# Windows: SystemRoot/ComSpec etc. existem em caixa mista; o filtro é case-insensitive.
CURSOR_ENV_ALLOW_WIN = frozenset({
    "PATH", "PATHEXT",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
    "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "ALLUSERSPROFILE",
    "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "USERNAME", "USER",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432", "OS",
    "TMP", "TEMP", "TMPDIR",
    "LANG", "LC_ALL", "LC_CTYPE",
}) | CURSOR_AUTH_ALLOW

CURSOR_ENV_ALLOW_POSIX = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "TMPDIR", "TMP", "TEMP",
    "LANG", "LC_ALL", "LC_CTYPE",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR",
}) | CURSOR_AUTH_ALLOW

# União usada em testes que não escolhem plataforma.
CURSOR_ENV_ALLOW = CURSOR_ENV_ALLOW_WIN | CURSOR_ENV_ALLOW_POSIX

# Keyring nativo do gh. GH_TOKEN/GITHUB_TOKEN ficam de fora de propósito.
GH_ENV_ALLOW = frozenset({
    "PATH", "PATHEXT", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "USERNAME", "USER", "OS",
    "GH_HOST",
    "LANG", "LC_ALL", "LC_CTYPE",
})

_BLOCK_PREFIX = ("FORGE_", "POSTGRES_", "GH_", "GITHUB_")
_BLOCK_EXACT = frozenset({
    "GH_TOKEN", "GITHUB_TOKEN", "DATABASE_URL", "FORGE_DATABASE_URL",
    "FORGE_DATABASE_MIGRATION_URL", "NODE_OPTIONS",
})


def cursor_env_allow(platform: str) -> frozenset[str]:
    if platform == "win32":
        return CURSOR_ENV_ALLOW_WIN
    return CURSOR_ENV_ALLOW_POSIX


def filter_env(src: Mapping[str, str], allow: frozenset[str], *,
               extra_allow: frozenset[str] | None = None) -> dict[str, str]:
    """Copia só chaves permitidas (comparação case-insensitive). Bloqueia tokens mesmo se listados."""
    allowed = {a.upper() for a in allow}
    if extra_allow:
        allowed |= {a.upper() for a in extra_allow}
    out: dict[str, str] = {}
    for key, value in src.items():
        ku = key.upper()
        if ku in _BLOCK_EXACT:
            continue
        if any(ku.startswith(p) for p in _BLOCK_PREFIX) and ku != "GH_HOST":
            continue
        if ku == "DATABASE_URL":
            continue
        if ku in allowed:
            out[key] = value
    return out


def assert_no_host_secrets(env: Mapping[str, str]) -> None:
    for key in env:
        ku = key.upper()
        if ku in ("GH_TOKEN", "GITHUB_TOKEN", "DATABASE_URL") or ku.startswith("FORGE_") or (
            ku.startswith("GH_") and ku != "GH_HOST"
        ) or ku.startswith("GITHUB_"):
            raise AssertionError(f"env vazou {key}")
