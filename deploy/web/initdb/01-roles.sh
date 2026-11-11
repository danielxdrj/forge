#!/bin/bash
# Primeiro boot do volume forge_pgdata: cria forge_app e forge_readonly a partir dos secrets.
# A senha fica gravada no volume; mudar depois é ALTER ROLE (ver runbook).
# Falha fechado se o arquivo de segredo faltar ou estiver vazio (incluindo o do leitor).
set -euo pipefail

read_secret() {
  local path="$1"
  local name
  name="$(basename "$path")"
  if [ ! -f "$path" ]; then
    echo "forge-init: segredo ausente: ${name}" >&2
    exit 1
  fi
  local value
  value="$(tr -d '\r\n' < "$path")"
  if [ -z "$value" ]; then
    echo "forge-init: segredo vazio: ${name}" >&2
    exit 1
  fi
  printf '%s' "$value"
}

sql_literal() {
  local value="$1"
  local delim="forgepw"
  while printf '%s' "$value" | grep -F -q "$delim"; do
    delim="${delim}x"
  done
  printf '$%s$%s$%s$' "$delim" "$value" "$delim"
}

APP_LIT="$(sql_literal "$(read_secret /run/secrets/forge_pg_app_password)")"
RO_LIT="$(sql_literal "$(read_secret /run/secrets/forge_pg_readonly_password)")"

{
  printf 'CREATE ROLE forge_app LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;\n' "$APP_LIT"
  printf 'CREATE ROLE forge_readonly LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;\n' "$RO_LIT"
  printf 'GRANT CONNECT ON DATABASE %s TO forge_app;\n' "$POSTGRES_DB"
  printf 'GRANT CONNECT ON DATABASE %s TO forge_readonly;\n' "$POSTGRES_DB"
  printf 'GRANT USAGE ON SCHEMA public TO forge_app;\n'
  printf 'GRANT USAGE ON SCHEMA public TO forge_readonly;\n'
} | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"
