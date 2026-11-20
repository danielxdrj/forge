"""Passos de uma execução de agente (tabela `agent_execution_events`, migração 0023).

Quem executa junta os passos em memória com `ExecutionSteps` e grava tudo na mesma transação
da linha de `agent_executions` (`insert_steps`). A mensagem passa por `redact` e é cortada: é
um registro do que aconteceu, não o conteúdo (prompt, resposta e dados ficam fora daqui).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ..logging import redact

KINDS = ("step", "model", "error")
MAX_MESSAGE = 300
MAX_STEPS = 50
STEP_COLUMNS = "execution_id, seq, at, kind, message, input_tokens, output_tokens, duration_ms"


class ExecutionSteps:
    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(UTC))
        self._items: list[dict] = []

    def step(self, message: str) -> None:
        self._add("step", message)

    def error(self, message: str) -> None:
        self._add("error", message)

    def model(self, message: str, *, usage: dict | None = None, duration_ms: int | None = None) -> None:
        data = usage or {}
        self._add(
            "model", message,
            input_tokens=_int(data.get("input_tokens")),
            output_tokens=_int(data.get("output_tokens")),
            duration_ms=_int(duration_ms),
        )

    @property
    def items(self) -> list[dict]:
        return list(self._items)

    def _add(self, kind: str, message: str, **extra) -> None:
        if len(self._items) >= MAX_STEPS:
            return
        text = redact(str(message or "")).strip()
        if len(text) > MAX_MESSAGE:
            text = text[: MAX_MESSAGE - 1] + "…"
        self._items.append({
            "kind": kind,
            "at": self._clock().isoformat(),
            "message": text,
            "input_tokens": extra.get("input_tokens"),
            "output_tokens": extra.get("output_tokens"),
            "duration_ms": extra.get("duration_ms"),
        })


def _int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def insert_steps(tx, execution_id: str, steps: ExecutionSteps | None) -> None:
    """Grava os passos dentro da transação `tx` que inseriu a execução."""
    if steps is None:
        return
    for seq, item in enumerate(steps.items, start=1):
        tx.execute(
            f"INSERT INTO agent_execution_events ({STEP_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (execution_id, seq, item["at"], item["kind"], item["message"],
             item["input_tokens"], item["output_tokens"], item["duration_ms"]),
        )


def load_steps(repo, execution_ids: list[str]) -> dict[str, list[dict]]:
    """Passos por execução, em ordem. Uma consulta para a página inteira de execuções."""
    if not execution_ids:
        return {}
    placeholders = ",".join("?" for _ in execution_ids)
    rows = repo.fetch(
        f"SELECT {STEP_COLUMNS} FROM agent_execution_events "
        f"WHERE execution_id IN ({placeholders}) ORDER BY execution_id, seq",
        tuple(execution_ids),
    )
    out: dict[str, list[dict]] = {}
    for execution_id, seq, at, kind, message, input_tokens, output_tokens, duration_ms in rows:
        out.setdefault(execution_id, []).append({
            "seq": seq, "at": at, "kind": kind, "message": message,
            "input_tokens": input_tokens, "output_tokens": output_tokens, "duration_ms": duration_ms,
        })
    return out
