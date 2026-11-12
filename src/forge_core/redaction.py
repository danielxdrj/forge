"""Redação de segredos em texto livre (corpo de issue, prompt). Nunca logar o original.

Complementa `logging.redact` com JWT, chaves privadas e connection strings com credencial.
O resultado substitui o valor por `***`; o texto original não é devolvido.
"""
from __future__ import annotations

import re

from .logging import redact as redact_log

REPLACEMENT = "***"

_GH_TOKEN = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}\b")
_GH_PAT = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}\b")
_AKIA = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_SECRET = re.compile(
    r"(?i)(\b(?:aws_secret_access_key|aws_session_token)\s*[=:]\s*)([^\s\"']+)"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_ASSIGN = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|senha|token|secret|api[_-]?key)\b\s*[=:]\s*)([^\s\"',;]+)"
)
_CONN = re.compile(
    r"(?i)\b((?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|"
    r"amqp|amqps|ftp|ftps|sftp|http|https|mssql|sqlserver))"
    r"://([^/\s:@]+):([^@/\s]+)@"
)
_PKEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)


def redact_secrets(text: str | None) -> str:
    """Mascara tokens, senhas, JWT, connection strings e chaves privadas."""
    if not text:
        return ""
    out = str(text)
    out = _PKEY.sub("-----BEGIN PRIVATE KEY-----\n***\n-----END PRIVATE KEY-----", out)
    out = _GH_TOKEN.sub(REPLACEMENT, out)
    out = _GH_PAT.sub(REPLACEMENT, out)
    out = _AKIA.sub(REPLACEMENT, out)
    out = _AWS_SECRET.sub(r"\1" + REPLACEMENT, out)
    out = _JWT.sub(REPLACEMENT, out)
    out = _CONN.sub(r"\1://***:***@", out)
    out = _ASSIGN.sub(r"\1" + REPLACEMENT, out)
    return redact_log(out)
