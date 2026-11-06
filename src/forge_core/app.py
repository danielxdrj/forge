"""Inicialização do Core: valida configuração, liga logging e devolve o contexto."""
from __future__ import annotations

import logging
import sys
from collections.abc import Mapping

from .config import Settings, load_settings
from .errors import ConfigError
from .logging import configure_logging


def start(env: Mapping[str, str] | None = None) -> Settings:
    settings = load_settings(env)
    configure_logging(settings.log_level)
    logging.getLogger("forge_core").info(
        "forge core iniciado", extra={"automation_enabled": settings.automation_enabled}
    )
    return settings


def main() -> int:
    try:
        start()
    except ConfigError as exc:
        print(f"forge-core: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
