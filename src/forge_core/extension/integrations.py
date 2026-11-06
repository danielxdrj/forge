from __future__ import annotations

from typing import Protocol


class Integration(Protocol):
    """Adaptador de sistema externo. O contrato só oferece operações de leitura por padrão."""

    name: str

    def operations(self) -> list[str]:
        """Operações que a integração declara oferecer."""
        ...

    def call(self, operation: str, params: dict) -> dict: ...
