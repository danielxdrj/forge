"""Aplica grants do escritor e do leitor depois das migrações (entrypoint do container)."""
from __future__ import annotations

import argparse
import json
import os
import sys

from ...errors import ConfigError
from .readonly import apply_readonly_grants
from .reprovision import ReprovisionError, reprovision


def bootstrap_grants(conn, app_role: str, readonly_role: str) -> list[str]:
    checks = list(reprovision(conn, app_role))
    checks += apply_readonly_grants(conn, readonly_role)
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bootstrap-grants")
    parser.add_argument("--app-role", default=os.environ.get("FORGE_PG_APP_USER", "forge_app"))
    parser.add_argument("--readonly-role", default=os.environ.get("FORGE_PG_READONLY_USER", "forge_readonly"))
    args = parser.parse_args(argv)
    url = os.environ.get("FORGE_DATABASE_MIGRATION_URL")
    if not url:
        print(json.dumps({"status": "error", "error": "migration_url_missing"}))
        return 2
    import psycopg

    try:
        with psycopg.connect(url) as conn:
            checks = bootstrap_grants(conn, args.app_role, args.readonly_role)
    except ReprovisionError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    except ConfigError as exc:
        print(json.dumps({"status": "error", "error": type(exc).__name__}))
        return 1
    except psycopg.Error:
        print(json.dumps({"status": "error", "error": "database_error"}))
        return 1
    print(json.dumps({"status": "ok", "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
