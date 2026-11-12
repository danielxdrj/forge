#!/bin/sh
# Root só para ajustar o volume de credenciais CLI; o processo da API corre como forge.
# Senhas do Postgres: o compose recusa secrets.environment em serviço read_only
# ("file is the sole supported option"). Plano B: env → arquivo no tmpfs /run/secrets
# (0600, uid 1000) e a variável some do processo antes do exec. Nenhuma senha em arquivo do host.
set -eu

materialize_secrets() {
  dest_dir=/run/secrets
  if [ ! -d "$dest_dir" ]; then
    echo "forge-web: tmpfs /run/secrets ausente" >&2
    exit 1
  fi
  umask 077
  _write_secret() {
    name="$1"
    var="$2"
    eval "val=\${$var-}"
    if [ -z "$val" ]; then
      echo "forge-web: segredo ausente: ${name}" >&2
      exit 1
    fi
    val=$(printf '%s' "$val" | tr -d '\r\n')
    if [ -z "$val" ]; then
      echo "forge-web: segredo vazio: ${name}" >&2
      exit 1
    fi
    printf '%s' "$val" > "${dest_dir}/${name}"
    unset "$var" || true
    val=""
  }
  _write_secret forge_pg_owner_password FORGE_PG_OWNER_PASSWORD
  _write_secret forge_pg_app_password FORGE_PG_APP_PASSWORD
  # Chave Fernet das conexões: opcional. Sem ela a área Conexões fica desligada.
  _write_optional_secret() {
    name="$1"
    var="$2"
    eval "val=\${$var-}"
    if [ -z "$val" ]; then
      unset "$var" || true
      return 0
    fi
    val=$(printf '%s' "$val" | tr -d '\r\n')
    if [ -z "$val" ]; then
      unset "$var" || true
      return 0
    fi
    printf '%s' "$val" > "${dest_dir}/${name}"
    chmod 0600 "${dest_dir}/${name}"
    unset "$var" || true
    val=""
  }
  _write_optional_secret forge_connections_key FORGE_CONNECTIONS_KEY
  unset FORGE_PG_OWNER_PASSWORD FORGE_PG_APP_PASSWORD FORGE_CONNECTIONS_KEY || true
  chmod 0600 "${dest_dir}/forge_pg_owner_password" "${dest_dir}/forge_pg_app_password"
}

if [ "$(id -u)" = "0" ]; then
  mkdir -p /home/forge
  chown -R forge:forge /home/forge
  materialize_secrets
  chown forge:forge /run/secrets/forge_pg_owner_password /run/secrets/forge_pg_app_password
  if [ -f /run/secrets/forge_connections_key ]; then
    chown forge:forge /run/secrets/forge_connections_key
  fi
  exec setpriv --reuid=1000 --regid=1000 --init-groups -- python -m forge_core.web
fi
materialize_secrets
exec python -m forge_core.web
