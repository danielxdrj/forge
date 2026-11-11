"""URLs de Postgres a partir de arquivos de segredo montados no container. Nunca loga o valor."""
from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path
from urllib.parse import quote

from ..errors import ConfigError

_DEFAULT_HOST = "forge_postgres"
_DEFAULT_PORT = "5432"
_DEFAULT_DB = "forge"
_DEFAULT_OWNER = "forge_owner"
_DEFAULT_APP = "forge_app"


class SecretMissingError(ConfigError):
    """Segredo ausente ou vazio. A mensagem cita o nome do arquivo, nunca o conteúdo."""


def read_secret_file(path: str | Path) -> str:
    """Lê um segredo de arquivo. Falha fechado se faltar, estiver vazio ou for só espaço/quebra de linha."""
    p = Path(path)
    if not p.is_file():
        raise SecretMissingError(f"segredo ausente: {p.name}")
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        raise SecretMissingError(f"segredo ilegível: {p.name}") from None
    value = raw.strip("\r\n")
    if not value or not value.strip():
        raise SecretMissingError(f"segredo vazio: {p.name}")
    return value


def build_postgres_url(user: str, password: str, host: str, port: str, database: str) -> str:
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{database}"
    )


def apply_database_urls_from_secret_files(env: MutableMapping[str, str] | None = None) -> None:
    """Preenche FORGE_DATABASE_URL (escritor) e FORGE_DATABASE_MIGRATION_URL (dono) a partir dos arquivos.

    Falha fechado se qualquer arquivo obrigatório faltar. Não registra as URLs.
    """
    env = os.environ if env is None else env
    owner_file = (env.get("FORGE_SECRET_OWNER_PASSWORD_FILE") or "").strip()
    app_file = (env.get("FORGE_SECRET_APP_PASSWORD_FILE") or "").strip()
    if not owner_file:
        raise SecretMissingError("FORGE_SECRET_OWNER_PASSWORD_FILE não configurado")
    if not app_file:
        raise SecretMissingError("FORGE_SECRET_APP_PASSWORD_FILE não configurado")
    owner_password = read_secret_file(owner_file)
    app_password = read_secret_file(app_file)
    host = (env.get("FORGE_PG_HOST") or _DEFAULT_HOST).strip()
    port = (env.get("FORGE_PG_PORT") or _DEFAULT_PORT).strip()
    database = (env.get("FORGE_PG_DB") or _DEFAULT_DB).strip()
    owner_user = (env.get("FORGE_PG_OWNER_USER") or _DEFAULT_OWNER).strip()
    app_user = (env.get("FORGE_PG_APP_USER") or _DEFAULT_APP).strip()
    env["FORGE_DATABASE_MIGRATION_URL"] = build_postgres_url(
        owner_user, owner_password, host, port, database
    )
    env["FORGE_DATABASE_URL"] = build_postgres_url(app_user, app_password, host, port, database)
