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


@dataclass(frozen=True)
class Settings:
    config_dir: str
    log_level: str = "INFO"
    automation_enabled: bool = True
    database_url: str | None = field(default=None, repr=False)
    database_migration_url: str | None = field(default=None, repr=False)
    agents_disabled: tuple[str, ...] = ()
    github_client_id: str | None = None


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
    if problems:
        raise ConfigError("Configuração inválida:\n- " + "\n- ".join(problems))
    return Settings(config_dir=config_dir, log_level=log_level, automation_enabled=automation, database_url=database_url,
                    database_migration_url=migration_url, agents_disabled=agents_disabled, github_client_id=client_id)


def is_automation_enabled(settings: Settings) -> bool:
    return settings.automation_enabled


def require_automation_enabled(settings: Settings) -> None:
    """Chave global de desligamento: chame antes de qualquer automação."""
    if not settings.automation_enabled:
        raise AutomationDisabledError("Automações desativadas (FORGE_AUTOMATION_ENABLED=false)")
