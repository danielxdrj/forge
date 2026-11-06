"""Adaptador de provedor de IA: só a interface. O provedor fica fora do contrato do agente (ADR-003).

Nenhuma implementação existe nesta etapa; um agente real receberá um adaptador por construtor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    usage: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None


class ProviderAdapter(Protocol):
    name: str

    def complete(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        """O conteúdo do prompt deve ter passado por redact() antes de sair do processo."""
        ...
