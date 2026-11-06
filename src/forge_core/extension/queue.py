from __future__ import annotations

from typing import Protocol


class TaskQueue(Protocol):
    """Fila simples (ADR-002). Implementação: FRG-40."""

    def put(self, item: dict) -> None: ...

    def get(self) -> dict | None: ...
