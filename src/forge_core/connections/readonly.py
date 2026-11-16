"""Travas de somente leitura em código, não só em instrução de prompt.

Três guardas:
- `ReadOnlyFTP`: subclasse de `ftplib.FTP` que só deixa passar comandos de leitura.
- `ReadOnlyPortainerClient`: só permite GET em caminhos de leitura da API Portainer.
- `assert_readonly_query` / `ReadOnlySqlGuard`: valida o texto da consulta (só
  SELECT/WITH/EXPLAIN/SHOW, sem DML) e abre a sessão/transação em modo leitura
  antes de executar.

Nenhuma destas classes aceita bypass por flag ou argumento: a lista permitida é fixa.
"""
from __future__ import annotations

import re
from ftplib import FTP
from urllib.request import Request, urlopen

from ..errors import ForgeError

POLICY_TEXT = (
    "Todas as conexões (FTP, banco de dados e Portainer) são somente leitura: a escrita, "
    "a exclusão e qualquer comando que altere o sistema remoto são bloqueados no código, "
    "não apenas por instrução ao modelo."
)


class ReadOnlyViolation(ForgeError):
    """Comando, caminho ou consulta de escrita recusado. `code` é estável; nunca ecoa o comando."""

    def __init__(self, code: str = "readonly_violation"):
        super().__init__(code)
        self.code = code


# --- FTP -------------------------------------------------------------------

FTP_ALLOWED_COMMANDS = frozenset({
    "LIST", "NLST", "MLSD", "RETR", "SIZE", "MDTM", "PWD", "CWD", "FEAT", "SYST",
    "TYPE", "PASV", "EPSV", "NOOP", "USER", "PASS", "QUIT", "OPTS",
})
_FTP_DENIED_HIGH_LEVEL = (
    "storbinary", "storlines", "stou", "delete", "rename", "mkd", "rmd",
    "sendcmd_site",
)


class ReadOnlyFTP(FTP):
    """FTP somente leitura: `sendcmd`/`voidcmd`/`putcmd` recusam qualquer comando fora da lista.

    Métodos de alto nível que só servem para escrever (`storbinary`, `delete`, `rename`,
    `mkd`, `rmd`, ...) são recusados antes de montar o comando, como defesa em profundidade.
    """

    def putcmd(self, line):
        self._check_command(line)
        return super().putcmd(line)

    def sendcmd(self, cmd):
        self._check_command(cmd)
        return super().sendcmd(cmd)

    def voidcmd(self, cmd):
        self._check_command(cmd)
        return super().voidcmd(cmd)

    @staticmethod
    def _check_command(line: str) -> None:
        text = (line or "").strip()
        if not text:
            raise ReadOnlyViolation("ftp_command_denied")
        parts = text.split(" ", 1)
        verb = parts[0].upper()
        if verb == "OPTS":
            rest = parts[1].strip().upper() if len(parts) > 1 else ""
            if not rest.startswith("UTF8"):
                raise ReadOnlyViolation("ftp_command_denied")
            return
        if verb not in FTP_ALLOWED_COMMANDS:
            raise ReadOnlyViolation("ftp_command_denied")

    def storbinary(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")

    def storlines(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")

    def stou(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")

    def delete(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")

    def rename(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")

    def mkd(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")

    def rmd(self, *args, **kwargs):
        raise ReadOnlyViolation("ftp_write_denied")


# --- Portainer ---------------------------------------------------------------

_PORTAINER_EXACT = frozenset({"/api/status", "/api/endpoints"})
_PORTAINER_PATTERNS = (
    re.compile(r"^/api/endpoints/\d+$"),
    re.compile(r"^/api/endpoints/\d+/docker/containers/json$"),
    re.compile(r"^/api/endpoints/\d+/docker/containers/[A-Za-z0-9_.:-]+/json$"),
    re.compile(r"^/api/endpoints/\d+/docker/containers/[A-Za-z0-9_.:-]+/logs$"),
    re.compile(r"^/api/endpoints/\d+/docker/containers/[A-Za-z0-9_.:-]+/stats$"),
)
_PORTAINER_DENY_MARKERS = (
    "/exec", "/restart", "/stop", "/kill", "/start", "/create", "/remove", "/update",
    "/attach", "/resize", "/archive", "/prune",
)


def portainer_path_allowed(path: str) -> bool:
    clean = (path or "").split("?", 1)[0]
    low = clean.lower()
    if any(marker in low for marker in _PORTAINER_DENY_MARKERS):
        return False
    if clean in _PORTAINER_EXACT:
        return True
    return any(pattern.fullmatch(clean) for pattern in _PORTAINER_PATTERNS)


class ReadOnlyPortainerClient:
    """Cliente Portainer que só permite GET em caminhos de leitura (status/endpoints/containers)."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0, urlopen_fn=urlopen):
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._urlopen = urlopen_fn

    def get(self, path: str):
        return self.request("GET", path)

    def request(self, method: str, path: str):
        if (method or "").upper() != "GET":
            raise ReadOnlyViolation("portainer_method_denied")
        if not (path or "").startswith("/api/") or not portainer_path_allowed(path):
            raise ReadOnlyViolation("portainer_path_denied")
        req = Request(
            self._base + path, method="GET",
            headers={"X-API-Key": self._token, "Accept": "application/json"},
        )
        return self._urlopen(req, timeout=self._timeout)


# --- SQL ---------------------------------------------------------------------

SQL_ALLOWED_START = frozenset({"SELECT", "WITH", "EXPLAIN", "SHOW"})
SQL_DENIED_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "COPY", "CALL", "DO", "VACUUM", "LOCK",
)
POSTGRES_READONLY_STATEMENTS = (
    "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
    "START TRANSACTION READ ONLY",
)
MYSQL_READONLY_STATEMENTS = ("SET SESSION TRANSACTION READ ONLY",)

_DENIED_RE = re.compile(
    r"\b(" + "|".join(SQL_DENIED_KEYWORDS) + r")\b|\bSET\s+ROLE\b", re.IGNORECASE,
)
_HEAD_RE = re.compile(r"^\s*([A-Za-z]+)")
_DOLLAR_TAG = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def strip_sql_comments_and_strings(sql: str) -> str:
    """Substitui comentários e literais (string/identificador/dollar-quote) por marcadores neutros.

    Usado só para checar a forma da consulta (palavra-chave, nº de comandos); nunca para executar.
    """
    text = sql or ""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and not (j + 1 < n and text[j + 1] == "'"):
                    break
                j += 1
            i = min(j + 1, n)
            out.append("''")
            continue
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 1
            i = min(j + 1, n)
            out.append('""')
            continue
        if ch == "$":
            m = _DOLLAR_TAG.match(text[i:])
            if m:
                tag = m.group(0)
                end = text.find(tag, i + len(tag))
                i = n if end == -1 else end + len(tag)
                out.append("''")
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def assert_readonly_query(sql: str) -> None:
    """Só SELECT/WITH/EXPLAIN/SHOW, um único comando, sem DML/DDL. Levanta `ReadOnlyViolation`."""
    raw = (sql or "").strip()
    if not raw:
        raise ReadOnlyViolation("sql_empty")
    stripped = strip_sql_comments_and_strings(raw)
    statements = [s for s in stripped.split(";") if s.strip()]
    if len(statements) != 1:
        raise ReadOnlyViolation("sql_multiple_statements")
    head_match = _HEAD_RE.match(stripped)
    head = head_match.group(1).upper() if head_match else ""
    if head not in SQL_ALLOWED_START:
        raise ReadOnlyViolation("sql_write_denied")
    if _DENIED_RE.search(stripped):
        raise ReadOnlyViolation("sql_write_denied")


def readonly_session_statements(dialect: str) -> tuple[str, ...]:
    d = (dialect or "").strip().lower()
    if d in ("postgres", "postgresql"):
        return POSTGRES_READONLY_STATEMENTS
    if d == "mysql":
        return MYSQL_READONLY_STATEMENTS
    raise ReadOnlyViolation("sql_dialect_unsupported")


class ReadOnlySqlGuard:
    """Abre a sessão em modo leitura (uma vez) e valida cada consulta antes de executar.

    `connection` é qualquer objeto DB-API (psycopg, PyMySQL/mysql-connector) com
    `.cursor()`. O guard nunca grava: consulta de escrita é recusada antes de chegar
    ao driver, e a sessão do banco também está em modo leitura (defesa em profundidade).
    """

    def __init__(self, connection, dialect: str):
        self._conn = connection
        self._dialect = dialect
        self._session_ready = False

    def _ensure_readonly_session(self) -> None:
        if self._session_ready:
            return
        cur = self._conn.cursor()
        try:
            for statement in readonly_session_statements(self._dialect):
                cur.execute(statement)
        finally:
            cur.close()
        self._session_ready = True

    def execute(self, sql: str, params: tuple | None = None):
        assert_readonly_query(sql)
        self._ensure_readonly_session()
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        return cur
