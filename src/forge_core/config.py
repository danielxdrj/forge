"""Configuração centralizada: lê variáveis de ambiente `FORGE_*` e valida na inicialização.

O Core só conhece configuração técnica. Agentes, prompts e permissões da empresa
ficam fora do Core (ADR-005); aqui há apenas o caminho para eles.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import AutomationDisabledError, ConfigError

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    config_dir: str
    log_level: str = "INFO"
    automation_enabled: bool = True


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

    if problems:
        raise ConfigError("Configuração inválida:\n- " + "\n- ".join(problems))
    return Settings(config_dir=config_dir, log_level=log_level, automation_enabled=automation)


def is_automation_enabled(settings: Settings) -> bool:
    return settings.automation_enabled


def require_automation_enabled(settings: Settings) -> None:
    """Chave global de desligamento: chame antes de qualquer automação."""
    if not settings.automation_enabled:
        raise AutomationDisabledError("Automações desativadas (FORGE_AUTOMATION_ENABLED=false)")
