"""Fonte única de contexto textual para o rascunho (ContextSource).

Nesta entrega só há texto: argumento (`--contexto`) e arquivo UTF-8 (`--arquivo`,
incluindo stdin `-`). Fontes futuras (print, anexo de imagem, Gmail, n8n) devem
implementar a mesma porta e ficar em etapa própria — não existem aqui.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ..errors import DraftError
from ..logging import redact

MAX_CONTEXT_BYTES = 64 * 1024
STDIN_NAME = "-"


class ContextSource(Protocol):
    kind: str

    def load(self) -> str:
        """Devolve texto UTF-8 já limitado. Sem shell, sem inferência."""
        ...


def decode_utf8(raw: bytes, *, origin: str) -> str:
    if len(raw) > MAX_CONTEXT_BYTES:
        raise DraftError("context_too_large")
    if b"\x00" in raw:
        raise DraftError("invalid_utf8", origin)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DraftError("invalid_utf8", origin) from exc
    text = redact(text).strip()
    if not text:
        raise DraftError("empty_context")
    return text


class TextContext:
    kind = "text"

    def __init__(self, value: str):
        self._value = value

    def load(self) -> str:
        return decode_utf8(self._value.encode("utf-8"), origin="contexto")


class FileContext:
    kind = "file"

    def __init__(self, path: str, stdin_read: Callable[[], bytes] | None = None):
        self._path = path
        self._stdin_read = stdin_read

    def load(self) -> str:
        if self._path == STDIN_NAME:
            if self._stdin_read is None:
                raise DraftError("empty_context")
            return decode_utf8(self._stdin_read(), origin="stdin")
        target = Path(self._path)
        if not target.is_file():
            raise DraftError("context_file")
        return decode_utf8(target.read_bytes(), origin=target.name)


def resolve_source(*, contexto: str | None, arquivo: str | None, positional: str | None,
                   stdin_read: Callable[[], bytes] | None = None) -> ContextSource:
    """Uma fonte só. `--contexto` e `--arquivo` são exclusivos; o posicional é alias de `--contexto`."""
    text = (contexto or "").strip() or None
    pos = (positional or "").strip() or None
    path = (arquivo or "").strip() or None
    chosen = [x for x in (text, pos, path) if x]
    if len(chosen) > 1:
        raise DraftError("context_ambiguous")
    if path:
        return FileContext(path, stdin_read=stdin_read)
    if text or pos:
        return TextContext(text or pos or "")
    raise DraftError("empty_context")
