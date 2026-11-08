"""Ponto de entrada DENTRO do container. Lê um JSON da entrada padrão e escreve uma linha JSON.

Não lê variáveis de ambiente de configuração, não abre banco e não grava auditoria. Imprime só o resultado
(a saída do agente vai para o descarte, para não corromper o protocolo).
"""
from __future__ import annotations

import contextlib
import importlib
import json
import sys

from ..tasks.model import Task
from .spec import AgentContext

REGISTRY_FACTORY = "forge_core.agents:default_registry"


def _task(payload: dict) -> Task:
    return Task(id=str(payload.get("task_id", ""))[:64], title=str(payload.get("title", ""))[:200],
                objective=str(payload.get("objective", ""))[:2000], context="", scope="", acceptance_criteria="",
                priority="normal", status="in_progress", assignee_kind="agent", assignee_id=None, start_date=None,
                due_date=None, completed_at=None, stage_id=None, parent_task_id=None, required=True, version=1,
                created_at="", updated_at="")


def _registry(path: str):
    module, attr = path.split(":")
    return getattr(importlib.import_module(module), attr)()


def run(request: dict, registry_factory: str = REGISTRY_FACTORY) -> dict:
    registry = _registry(registry_factory)
    agent = registry.get(str(request.get("agent", "")))
    if agent is None:
        return {"status": "error", "error": "unknown_agent"}
    ctx = AgentContext(task=_task(request.get("payload") or {}), actor="agente:sandbox")
    try:
        with contextlib.redirect_stdout(sys.stderr):
            outcome = agent.run(ctx)
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__[:80], "logs": ctx.logs}
    if outcome.status not in ("success", "failure"):
        return {"status": "error", "error": "invalid_outcome", "logs": ctx.logs}
    return {"status": outcome.status, "summary": outcome.summary[:2000], "logs": ctx.logs}


def main() -> None:
    factory = sys.argv[1] if len(sys.argv) > 1 else REGISTRY_FACTORY
    request = json.loads(sys.stdin.read(64 * 1024))
    result = run(request, factory)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
