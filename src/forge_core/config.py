"""Configuração centralizada: lê variáveis de ambiente `FORGE_*` e valida na inicialização.

O Core só conhece configuração técnica. Agentes, prompts e permissões da empresa
ficam fora do Core (ADR-005); aqui há apenas o caminho para eles.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import AutomationDisabledError, ConfigError

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


_DEFAULT_WEB_HOSTS = (
    "127.0.0.1:8090",
    "localhost:8090",
    "127.0.0.1:8091",
    "localhost:8091",
)
_HOST = re.compile(r"^[A-Za-z0-9.-]+:[0-9]{1,5}$")
_DEFAULT_SESSION_TTL = 7 * 24 * 3600
_DEFAULT_GRAPH_DIR = "/graphs"
_DEFAULT_GRAPH_POLL = 3600
_MAX_GRAPH_POLL = 7 * 24 * 3600
_DEFAULT_GRAPH_NODE_LIMIT = 500
_DEFAULT_GRAPH_EDGE_LIMIT = 1500


@dataclass(frozen=True)
class Settings:
    config_dir: str
    log_level: str = "INFO"
    automation_enabled: bool = True
    database_url: str | None = field(default=None, repr=False)
    database_migration_url: str | None = field(default=None, repr=False)
    agents_disabled: tuple[str, ...] = ()
    github_client_id: str | None = None
    session_ttl_seconds: int = _DEFAULT_SESSION_TTL
    cookie_secure: bool = False
    web_hosts: tuple[str, ...] = _DEFAULT_WEB_HOSTS
    trust_forwarded: bool = False
    trusted_proxies: tuple[str, ...] = ()
    obsidian_vault: str | None = None
    obsidian_allow: tuple[str, ...] = ()
    graph_dir: str = _DEFAULT_GRAPH_DIR
    graph_poll_seconds: int = _DEFAULT_GRAPH_POLL
    graphify_bin: str = "graphify"
    graph_node_limit: int = _DEFAULT_GRAPH_NODE_LIMIT
    graph_edge_limit: int = _DEFAULT_GRAPH_EDGE_LIMIT


def _allow_folders(raw: str) -> tuple[str, ...]:
    """Pastas relativas do vault. Sem `..`, sem caminho absoluto."""
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        item = part.strip().replace("\\", "/").strip("/")
        if not item:
            continue
        bits = [b for b in item.split("/") if b and b != "."]
        if not bits or any(b == ".." for b in bits):
            continue
        cleaned = "/".join(bits)
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return tuple(out)


def _bool(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} deve ser booleano (true/false), recebido {raw!r}")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Carrega e valida a configuração. Levanta ConfigError listando todos os problemas."""
    env = os.environ if env is None else env
    problems: list[str] = []

    config_dir = env.get("FORGE_CONFIG_DIR", "").strip()
    if not config_dir:
        problems.append("FORGE_CONFIG_DIR é obrigatória (diretório da configuração da empresa)")

    log_level = env.get("FORGE_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in _LOG_LEVELS:
        problems.append(f"FORGE_LOG_LEVEL inválida: {log_level!r}; use um de {', '.join(_LOG_LEVELS)}")

    automation = True
    try:
        automation = _bool("FORGE_AUTOMATION_ENABLED", env.get("FORGE_AUTOMATION_ENABLED", "true"))
    except ValueError as exc:
        problems.append(str(exc))

    database_url = env.get("FORGE_DATABASE_URL", "").strip() or None
    if database_url and not database_url.startswith(("sqlite:///", "postgresql://", "postgres://")):
        problems.append("FORGE_DATABASE_URL inválida: use sqlite:/// ou postgresql://")

    migration_url = env.get("FORGE_DATABASE_MIGRATION_URL", "").strip() or None
    if migration_url and not migration_url.startswith(("sqlite:///", "postgresql://", "postgres://")):
        problems.append("FORGE_DATABASE_MIGRATION_URL inválida: use sqlite:/// ou postgresql://")

    agents_disabled = tuple(
        n.strip().lower() for n in env.get("FORGE_AGENTS_DISABLED", "").split(",") if n.strip()
    )

    client_id = env.get("FORGE_GITHUB_CLIENT_ID", "").strip() or None
    if client_id and not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", client_id):
        problems.append("FORGE_GITHUB_CLIENT_ID inválido: use só o client id público do OAuth App")

    ttl_raw = env.get("FORGE_SESSION_TTL_SECONDS", str(_DEFAULT_SESSION_TTL)).strip()
    ttl = _DEFAULT_SESSION_TTL
    try:
        ttl = int(ttl_raw)
        if ttl < 60 or ttl > 7 * 24 * 3600:
            problems.append("FORGE_SESSION_TTL_SECONDS inválido: use um inteiro entre 60 e 604800")
    except ValueError:
        problems.append("FORGE_SESSION_TTL_SECONDS inválido: use um inteiro entre 60 e 604800")

    cookie_secure = False
    try:
        cookie_secure = _bool("FORGE_COOKIE_SECURE", env.get("FORGE_COOKIE_SECURE", "false"))
    except ValueError as exc:
        problems.append(str(exc))

    hosts_raw = env.get("FORGE_WEB_HOSTS", ",".join(_DEFAULT_WEB_HOSTS))
    web_hosts = tuple(h.strip().lower() for h in hosts_raw.split(",") if h.strip())
    if not web_hosts:
        problems.append("FORGE_WEB_HOSTS inválido: informe ao menos um Host permitido (host:porta)")
    for host in web_hosts:
        if not _HOST.fullmatch(host):
            problems.append("FORGE_WEB_HOSTS inválido: use host:porta (ex.: 127.0.0.1:8090)")
            break

    trust_forwarded = False
    try:
        trust_forwarded = _bool("FORGE_TRUST_FORWARDED", env.get("FORGE_TRUST_FORWARDED", "false"))
    except ValueError as exc:
        problems.append(str(exc))
    trusted_proxies = tuple(
        p.strip() for p in env.get("FORGE_TRUSTED_PROXIES", "").split(",") if p.strip()
    )
    if trust_forwarded and not trusted_proxies:
        problems.append("FORGE_TRUST_FORWARDED=true exige FORGE_TRUSTED_PROXIES (IPs do proxy na rede compose)")

    vault_raw = env.get("FORGE_OBSIDIAN_VAULT", "").strip()
    obsidian_vault = vault_raw or None
    if obsidian_vault and not os.path.isabs(obsidian_vault):
        problems.append("FORGE_OBSIDIAN_VAULT inválido: use um caminho absoluto no container (ex.: /vault)")

    obsidian_allow = _allow_folders(env.get("FORGE_OBSIDIAN_ALLOW", ""))

    graph_dir = env.get("FORGE_GRAPH_DIR", _DEFAULT_GRAPH_DIR).strip() or _DEFAULT_GRAPH_DIR
    if not os.path.isabs(graph_dir):
        problems.append("FORGE_GRAPH_DIR inválido: use um caminho absoluto no container (ex.: /graphs)")

    poll_raw = env.get("FORGE_GRAPH_POLL_SECONDS", str(_DEFAULT_GRAPH_POLL)).strip()
    graph_poll = _DEFAULT_GRAPH_POLL
    try:
        graph_poll = int(poll_raw)
        if graph_poll < 0 or graph_poll > _MAX_GRAPH_POLL:
            problems.append("FORGE_GRAPH_POLL_SECONDS inválido: use um inteiro entre 0 e 604800 (0 desliga o poll)")
    except ValueError:
        problems.append("FORGE_GRAPH_POLL_SECONDS inválido: use um inteiro entre 0 e 604800 (0 desliga o poll)")

    graphify_bin = env.get("FORGE_GRAPHIFY_BIN", "graphify").strip() or "graphify"

    node_limit = _DEFAULT_GRAPH_NODE_LIMIT
    node_raw = env.get("FORGE_GRAPH_NODE_LIMIT", str(_DEFAULT_GRAPH_NODE_LIMIT)).strip()
    try:
        node_limit = int(node_raw)
        if node_limit < 50 or node_limit > 5000:
            problems.append("FORGE_GRAPH_NODE_LIMIT inválido: use um inteiro entre 50 e 5000")
    except ValueError:
        problems.append("FORGE_GRAPH_NODE_LIMIT inválido: use um inteiro entre 50 e 5000")

    edge_limit = _DEFAULT_GRAPH_EDGE_LIMIT
    edge_raw = env.get("FORGE_GRAPH_EDGE_LIMIT", str(_DEFAULT_GRAPH_EDGE_LIMIT)).strip()
    try:
        edge_limit = int(edge_raw)
        if edge_limit < 100 or edge_limit > 20000:
            problems.append("FORGE_GRAPH_EDGE_LIMIT inválido: use um inteiro entre 100 e 20000")
    except ValueError:
        problems.append("FORGE_GRAPH_EDGE_LIMIT inválido: use um inteiro entre 100 e 20000")

    if problems:
        raise ConfigError("Configuração inválida:\n- " + "\n- ".join(problems))
    return Settings(
        config_dir=config_dir, log_level=log_level, automation_enabled=automation, database_url=database_url,
        database_migration_url=migration_url, agents_disabled=agents_disabled, github_client_id=client_id,
        session_ttl_seconds=ttl, cookie_secure=cookie_secure, web_hosts=web_hosts,
        trust_forwarded=trust_forwarded, trusted_proxies=trusted_proxies,
        obsidian_vault=obsidian_vault, obsidian_allow=obsidian_allow,
        graph_dir=graph_dir, graph_poll_seconds=graph_poll, graphify_bin=graphify_bin,
        graph_node_limit=node_limit, graph_edge_limit=edge_limit,
    )


def is_automation_enabled(settings: Settings) -> bool:
    return settings.automation_enabled


def require_automation_enabled(settings: Settings) -> None:
    """Chave global de desligamento: chame antes de qualquer automação."""
    if not settings.automation_enabled:
        raise AutomationDisabledError("Automações desativadas (FORGE_AUTOMATION_ENABLED=false)")
