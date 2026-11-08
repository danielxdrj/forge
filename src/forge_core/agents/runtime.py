"""Resultado de execução de agente (contrato comum do Orchestrator).

Não há runtime em thread na API pública: a execução de agentes passa só por `IsolatedRuntime` (sandbox.py,
ADR-013). O dublê em thread existe apenas em tests/core/inprocess_runtime.py, para testes de lógica.
"""
from __future__ import annotations

from dataclasses import dataclass

from .spec import AgentOutcome


@dataclass(frozen=True)
class RunResult:
    status: str  # success | failure | error | timeout | cancelled
    outcome: AgentOutcome | None
    error: str | None
    started_at: str
    finished_at: str
    logs: list[str]
