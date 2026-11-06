"""Agent Runtime mínimo: executa um agente com timeout, cancelamento e erros tratados.

Limite aceito: o agente roda numa thread daemon. Timeout e cancelamento são cooperativos (o runtime
sinaliza `cancel_event` e deixa de esperar), mas NÃO matam a thread. Isolamento de verdade: FRG-6.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from ..errors import AgentFailure
from ..logging import redact
from .spec import Agent, AgentContext, AgentOutcome

_MAX_ERROR = 2000


@dataclass(frozen=True)
class RunResult:
    status: str  # success | failure | error | timeout | cancelled
    outcome: AgentOutcome | None
    error: str | None
    started_at: str
    finished_at: str
    logs: list[str]


class AgentRuntime:
    def __init__(self, poll_seconds: float = 0.01):
        self._poll = poll_seconds

    def execute(self, agent: Agent, ctx: AgentContext, timeout: float | None = None) -> RunResult:
        timeout = agent.spec.timeout_seconds if timeout is None else timeout
        started = datetime.now(timezone.utc).isoformat()
        box: dict = {}

        def target():
            try:
                box["outcome"] = agent.run(ctx)
            except Exception as exc:  # código de agente é terceiros: nunca derruba o orquestrador
                box["exc"] = exc

        thread = threading.Thread(target=target, name=f"agent-{agent.spec.name}", daemon=True)
        thread.start()
        deadline = time.monotonic() + timeout
        while thread.is_alive():
            if ctx.cancel_event.is_set():
                return self._result("cancelled", None, "cancelado", started, ctx)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                ctx.cancel_event.set()
                return self._result("timeout", None, f"timeout após {timeout}s", started, ctx)
            thread.join(min(self._poll, remaining))

        if ctx.cancel_event.is_set():  # cancelado durante a execução: descarta o resultado, mesmo que tenha chegado
            return self._result("cancelled", None, "cancelado", started, ctx)
        if "exc" in box:
            exc = box["exc"]
            if isinstance(exc, AgentFailure):
                error = f"AgentFailure: {redact(str(exc))}"[:_MAX_ERROR]
            else:
                error = type(exc).__name__  # a mensagem pode ecoar o contexto da tarefa
            return self._result("error", None, error, started, ctx)
        outcome = box.get("outcome")
        if not isinstance(outcome, AgentOutcome) or outcome.status not in ("success", "failure"):
            return self._result("error", None, "InvalidOutcome", started, ctx)
        status = "success" if outcome.status == "success" else "failure"
        return self._result(status, outcome, None, started, ctx)

    @staticmethod
    def _result(status, outcome, error, started, ctx) -> RunResult:
        return RunResult(status, outcome, error, started, datetime.now(timezone.utc).isoformat(), ctx.logs)
