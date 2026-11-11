import pytest

from forge_core.storage.secrets import (
    SecretMissingError,
    apply_database_urls_from_secret_files,
    build_postgres_url,
    read_secret_file,
)


def test_missing_secret_file_fails_closed_without_echoing_path_content(tmp_path):
    with pytest.raises(SecretMissingError) as exc:
        read_secret_file(tmp_path / "forge_pg_app_password")
    assert "forge_pg_app_password" in str(exc.value)
    assert "ausente" in str(exc.value)


def test_empty_secret_fails_closed(tmp_path):
    p = tmp_path / "forge_pg_owner_password"
    p.write_text("\n", encoding="utf-8")
    with pytest.raises(SecretMissingError, match="vazio"):
        read_secret_file(p)


def test_apply_builds_urls_from_files_and_does_not_keep_raw_in_error(tmp_path):
    owner = tmp_path / "owner"
    app = tmp_path / "app"
    owner.write_text("dono/com:especial\n", encoding="utf-8")
    app.write_text("app senha\n", encoding="utf-8")
    env = {
        "FORGE_SECRET_OWNER_PASSWORD_FILE": str(owner),
        "FORGE_SECRET_APP_PASSWORD_FILE": str(app),
        "FORGE_PG_HOST": "forge_postgres",
        "FORGE_PG_PORT": "5432",
        "FORGE_PG_DB": "forge",
        "FORGE_PG_OWNER_USER": "forge_owner",
        "FORGE_PG_APP_USER": "forge_app",
    }
    apply_database_urls_from_secret_files(env)
    assert "forge_owner" in env["FORGE_DATABASE_MIGRATION_URL"]
    assert "forge_app" in env["FORGE_DATABASE_URL"]
    assert "dono%2Fcom%3Aespecial" in env["FORGE_DATABASE_MIGRATION_URL"]
    assert env["FORGE_DATABASE_URL"].startswith("postgresql://")


def test_missing_env_path_fails_closed():
    with pytest.raises(SecretMissingError, match="FORGE_SECRET_OWNER_PASSWORD_FILE"):
        apply_database_urls_from_secret_files({})


def test_build_postgres_url_encodes_password():
    url = build_postgres_url("u", "a b", "h", "5432", "db")
    assert "a%20b" in url
    assert "a b" not in url
