"""DUBLÊ DE TESTE do transporte Docker (nunca usado em produção).

Os testes locais de dispatch precisam de Docker para o caminho real. Este dublê substitui só o transporte:
executa o agente recebido, com o mesmo contrato de resultado, para que a lógica do Orchestrator seja testada
sem Docker. O isolamento real é provado em tests/sandbox, com o Docker do runner de CI.
"""
from forge_core.agents.sandbox import SandboxResult
from inprocess_runtime import InProcessRuntime
from forge_core.agents.spec import AgentContext
from forge_core.tasks.model import Task


class InProcessSandbox:
    def run(self, agent, payload, timeout, cancel_event=None):
        task = Task(payload.get("task_id", ""), payload.get("title", ""), payload.get("objective", ""), "", "", "",
                    "normal", "in_progress", None, None, None, None, None, None, None, True, 1, "", "")
        ctx = AgentContext(task=task, actor="agente:sandbox")
        if cancel_event is not None:
            ctx.cancel_event = cancel_event
        res = InProcessRuntime().execute(agent, ctx, timeout)
        if res.status in ("success", "failure"):
            o = res.outcome
            return SandboxResult(res.status, o.summary, res.logs, usage=o.usage, cost=o.cost)
        if res.status == "timeout":
            return SandboxResult("timeout", error="timeout")
        if res.status == "cancelled":
            return SandboxResult("cancelled", error="cancelled")
        return SandboxResult("error", res.logs, error=res.error or "error")
