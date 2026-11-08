"""DUBLÊ DE TESTE: execução de agente em thread, só para testar lógica de timeout, cancelamento e selamento.

NÃO existe em produção. Herda os gates de IsolatedRuntime (automação, agentes desativados, só read) e
sobrescreve apenas a execução. Os testes de isolamento real estão em tests/sandbox (Docker no CI).
"""
import threading
import time
from datetime import datetime, timezone

from forge_core.agents.runtime import RunResult
from forge_core.agents.sandbox import IsolatedRuntime


class InProcessRuntime(IsolatedRuntime):
    def __init__(self, poll_seconds: float = 0.01, settings=None):
        super().__init__(sandbox=None, settings=settings)
        self._poll = poll_seconds

    def execute(self, agent, ctx, timeout=None) -> RunResult:
        self.check_allowed(agent)
        timeout = agent.spec.timeout_seconds if timeout is None else timeout
        started = datetime.now(timezone.utc).isoformat()
        box: dict = {}

        def target():
            try:
                outcome = agent.run(ctx)
                if not ctx.sealed:
                    box["outcome"] = outcome
            except Exception as exc:
                if not ctx.sealed:
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

        if ctx.cancel_event.is_set():
            return self._result("cancelled", None, "cancelado", started, ctx)
        if "exc" in box:
            exc = box["exc"]
            from forge_core.errors import AgentFailure
            from forge_core.logging import redact

            if isinstance(exc, AgentFailure):
                return self._result("error", None, f"AgentFailure: {redact(str(exc))}"[:2000], started, ctx)
            return self._result("error", None, type(exc).__name__, started, ctx)
        outcome = box.get("outcome")
        from forge_core.agents.spec import AgentOutcome

        if not isinstance(outcome, AgentOutcome) or outcome.status not in ("success", "failure"):
            return self._result("error", None, "InvalidOutcome", started, ctx)
        return self._result(outcome.status, outcome, None, started, ctx)

    @staticmethod
    def _result(status, outcome, error, started, ctx) -> RunResult:
        ctx.seal()
        return RunResult(status, outcome, error, started, datetime.now(timezone.utc).isoformat(), ctx.logs)
