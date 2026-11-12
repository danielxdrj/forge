"""Sobe o painel: lê segredos, migra, aplica grants, semente e inicia o uvicorn (um worker)."""
from __future__ import annotations

import os
import sys

from ..config import load_settings
from ..errors import ConfigError
from ..logging import configure_logging
from ..storage.provisioning.bootstrap import bootstrap_grants
from ..storage.secrets import SecretMissingError, apply_database_urls_from_secret_files
from ..storage.seed import seed_allowed_repos
from ..storage.sql import open_repository
from .app import create_app


def main() -> int:
    try:
        apply_database_urls_from_secret_files()
        settings = load_settings()
        configure_logging(settings.log_level)
        if not settings.database_url or not settings.database_migration_url:
            raise ConfigError("URLs de banco ausentes depois dos arquivos de segredo")
        repo = open_repository(settings.database_url, settings.database_migration_url)
        import psycopg

        app_role = os.environ.get("FORGE_PG_APP_USER", "forge_app")
        readonly_role = os.environ.get("FORGE_PG_READONLY_USER", "forge_readonly")
        with psycopg.connect(settings.database_migration_url) as conn:
            bootstrap_grants(conn, app_role, readonly_role)
        seed_allowed_repos(repo)
        from ..draft.cursor_cli import CursorCliAdapter
        from ..draft.github_gh import GhCli

        provider = CursorCliAdapter()
        gh_cli = GhCli(bin_path=os.environ.get("FORGE_GH_BIN", "gh").strip() or "gh")
        app = create_app(repo, settings, provider=provider, gh=gh_cli)
        indexer = getattr(app.state, "graphs", None)
        if indexer is not None:
            indexer.start()
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8091, workers=1)
        return 0
    except SecretMissingError as exc:
        print(f"forge-web: {exc}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(f"forge-web: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
