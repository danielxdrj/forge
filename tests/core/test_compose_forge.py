"""Checagens estáticas do docker-compose.forge.yml e do nginx (sem subir serviços)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.forge.yml").read_text(encoding="utf-8")
NGINX = (ROOT / "deploy/frontend/nginx.conf").read_text(encoding="utf-8")
FRONTEND_DOCKERFILE = (ROOT / "deploy/frontend/Dockerfile").read_text(encoding="utf-8")
BACKEND_DOCKERFILE = (ROOT / "deploy/web/Dockerfile").read_text(encoding="utf-8")


def test_compose_project_and_three_container_names():
    assert re.search(r"(?m)^name:\s*forge\s*$", COMPOSE)
    assert "container_name: forge_postgres" in COMPOSE
    assert "container_name: forge_backend" in COMPOSE
    assert "container_name: forge_frontend" in COMPOSE
    assert COMPOSE.count("container_name:") == 3
    assert "forge_pgdata" in COMPOSE
    assert "forge_cli_home" in COMPOSE


def test_ports_are_loopback_only_frontend_8090_backend_not_published():
    assert "127.0.0.1:${FORGE_FRONTEND_HOST_PORT:-8090}:8080" in COMPOSE
    assert "127.0.0.1:${FORGE_PG_HOST_PORT:-5433}:5432" in COMPOSE
    assert "8091:8091" not in COMPOSE
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


def test_backend_trusts_forwarded_only_from_frontend_hostname():
    assert 'FORGE_TRUST_FORWARDED: "true"' in COMPOSE
    assert "FORGE_TRUSTED_PROXIES: forge_frontend" in COMPOSE


def test_postgres_image_is_pinned_by_digest():
    assert re.search(r"postgres:16-bookworm@sha256:[0-9a-f]{64}", COMPOSE)


def test_backend_dockerfile_runs_as_user_forge():
    assert re.search(r"(?m)^USER forge\s*$", BACKEND_DOCKERFILE)


def test_backend_is_read_only_with_run_secrets_tmpfs():
    backend = COMPOSE.split("forge_backend:")[1].split("forge_frontend:")[0]
    assert "read_only: true" in backend
    assert "/run/secrets" in backend
    assert "mode=0700" in backend
    assert "uid=1000" in backend
    assert "gid=1000" in backend
    assert not re.search(r"(?m)^\s+secrets:\s*$", backend)
    assert "FORGE_SECRET_OWNER_PASSWORD_FILE: /run/secrets/forge_pg_owner_password" in backend
    assert "FORGE_SECRET_CONNECTIONS_KEY_FILE: /run/secrets/forge_connections_key" in backend
    assert "FORGE_CONNECTIONS_KEY:" in backend
    assert "FORGE_WEB_HOSTS:" in backend
    assert "FORGE_FRONTEND_HOST_PORT:-8090" in backend
    assert "FORGE_SESSION_TTL_SECONDS:" in backend


def test_shell_and_dockerfiles_have_no_cr():
    paths = list((ROOT / "deploy").rglob("*.sh"))
    paths += list((ROOT / "deploy").rglob("*.conf"))
    paths += list(ROOT.glob("Dockerfile*"))
    paths += list((ROOT / "deploy").rglob("Dockerfile*"))
    cr = [str(p.relative_to(ROOT)) for p in paths if p.is_file() and b"\r" in p.read_bytes()]
    assert cr == []
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in gitattributes
    assert "*.conf text eol=lf" in gitattributes
    assert "Dockerfile* text eol=lf" in gitattributes
    assert "b'\\r'" in BACKEND_DOCKERFILE
    assert "check-lf-01-roles.sh" in BACKEND_DOCKERFILE


def test_nginx_proxies_api_sets_forwarded_headers_and_csp():
    assert "location = /conexoes" in NGINX
    assert "location /api/" in NGINX
    assert "proxy_pass http://forge_backend:8091" in NGINX
    assert "proxy_set_header Host $http_host" in NGINX
    assert "proxy_set_header X-Forwarded-Host $http_host" in NGINX
    assert "proxy_set_header X-Forwarded-For" in NGINX
    assert "proxy_set_header X-Forwarded-Proto" in NGINX
    assert "default-src 'self'" in NGINX
    assert "frame-ancestors 'none'" in NGINX
    assert "nosniff" in NGINX
    assert "no-referrer" in NGINX
    assert "unsafe-inline" not in NGINX
    assert "listen 8080" in NGINX
    assert "nginxinc/nginx-unprivileged" in FRONTEND_DOCKERFILE
    assert "@sha256:" in FRONTEND_DOCKERFILE
    html = (ROOT / "deploy/frontend/html/index.html").read_text(encoding="utf-8")
    assert "<script src=\"/app.js\"" in html
    assert "onclick=" not in html
    js = (ROOT / "deploy/frontend/html/app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js
    assert "textContent" in js
    assert "draft-body" in js
    assert "pending_fields" in js
    assert "fieldsError" in js
    assert "Gerar de novo" in js
    assert "Publicadas" in js
    assert "Rascunhos" in js
    assert "/discard" in js
    assert "publishedIssueLink" in js
    assert 'setAttribute("target", "_blank")' in js
    anchors = re.findall(r'el\("a", \{[^}]+\}', js)
    assert anchors
    for spec in anchors:
        assert 'target: "_blank"' in spec
        assert 'rel: "noopener noreferrer"' in spec
    assert "safeLink(state.pending.verification_uri)" in js
    assert "safeLink(links.issue_url)" in js
    assert "safeLink(links.pr_url)" in js
    assert "publishedIssueLink(task.issue_url)" in js
    assert "safeLink(task.pr_url" in js
    conexoes = (ROOT / "deploy/frontend/html/conexoes.js").read_text(encoding="utf-8")
    assert "innerHTML" not in conexoes
    assert "textContent" in conexoes
    assert "/api/connections" in conexoes
    assert "secret_set" in conexoes
    assert "Testar conexão" in conexoes
    html_conn = (ROOT / "deploy/frontend/html/conexoes.html").read_text(encoding="utf-8")
    assert "<script src=\"/conexoes.js\"" in html_conn
    entrypoint = (ROOT / "deploy/web/entrypoint.sh").read_text(encoding="utf-8")
    assert "forge_connections_key" in entrypoint
    assert "FORGE_CONNECTIONS_KEY" in entrypoint
    assert "\r" not in entrypoint
