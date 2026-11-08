"""Logging estruturado básico (uma linha JSON por evento) com redação de segredos."""
from __future__ import annotations

import json
import logging
import re
import sys

_AUTH = re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\r\n]+)")
# Bearer/Basic: o valor pode ter espaços ou aspas; mascara até o fim da linha (conservador).
_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[^\r\n]+")
_SECRET = re.compile(r"(?i)(token|secret|password|senha|key)(\"?\s*[:=]\s*\"?)([^\s\",]+)")
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


TOKEN_SHAPE = re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[0-9A-Z]{12,})")


def redact(text: str) -> str:
    text = TOKEN_SHAPE.sub("***", text)
    text = _AUTH.sub(r"\1***", text)
    text = _SCHEME.sub(r"\1 ***", text)
    return _SECRET.sub(r"\1\2***", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED:
                data[k] = redact(f"{k}={v}").split("=", 1)[1]
        return json.dumps(data, ensure_ascii=False)


def configure_logging(level: str = "INFO", stream=None) -> None:
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("forge_core")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
