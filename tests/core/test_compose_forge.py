"""Checagens estáticas do docker-compose.forge.yml (sem subir serviços)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.forge.yml").read_text(encoding="utf-8")


def test_compose_project_and_container_names():
    assert re.search(r"(?m)^name:\s*forge\s*$", COMPOSE)
    assert "container_name: forge_postgres" in COMPOSE
    assert "container_name: forge_backend" in COMPOSE
    assert "container_name: forge_frontend" not in COMPOSE
    assert "forge_frontend" in COMPOSE  # planejado no PR B, citado no comentário
    assert "forge_pgdata" in COMPOSE
    assert "forge_cli_home" in COMPOSE


def test_ports_are_loopback_only_and_configurable():
    assert "127.0.0.1:${FORGE_PG_HOST_PORT:-5433}:5432" in COMPOSE
    assert "127.0.0.1:${FORGE_BACKEND_HOST_PORT:-8091}:8091" in COMPOSE
    assert "0.0.0.0" not in COMPOSE
    for match in re.finditer(r'-\s*"([^"]+)"', COMPOSE):
        mapping = match.group(1)
        if mapping.count(":") >= 2:
            assert mapping.startswith("127.0.0.1:"), mapping


def test_no_host_keyring_home_or_docker_sock_mounts():
    lowered = COMPOSE.lower()
    for needle in (
        "docker.sock",
        "${home}",
        "${userprofile}",
        "appdata",
        "keyring",
        "~/.config/gh",
        "~/.config",
        "%appdata%",
        "%userprofile%",
    ):
        assert needle not in lowered
    assert "./deploy/web/initdb:/docker-entrypoint-initdb.d:ro" in COMPOSE
    assert "docker.sock" not in COMPOSE
    assert "~/ " not in COMPOSE
    assert "${HOME}" not in COMPOSE


def test_secrets_come_from_environment_not_files():
    assert "environment: FORGE_PG_OWNER_PASSWORD" in COMPOSE
    assert "environment: FORGE_PG_APP_PASSWORD" in COMPOSE
    assert "environment: FORGE_PG_READONLY_PASSWORD" in COMPOSE
    assert "POSTGRES_PASSWORD_FILE" in COMPOSE
    assert not re.search(r"(?m)^\s+file:", COMPOSE)
    for banned in ("GH_TOKEN", "GITHUB_TOKEN"):
        assert banned not in COMPOSE
