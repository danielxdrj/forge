from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class AgentResult:
    summary: str
    artifacts: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)


class Agent(Protocol):
    """Contrato mínimo de agente (arquitetura-alvo, seção 5)."""

    name: str
    active: bool

    def run(self, context: dict) -> AgentResult: ...
