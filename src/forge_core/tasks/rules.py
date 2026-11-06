"""Regras de domínio das tarefas (ADR-010). Funções puras: recebem estados, não tocam no banco."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from ..errors import TaskRuleError
from .model import AssigneeKind, Priority, TaskStatus as S

TRANSITIONS: dict[str, tuple[str, ...]] = {
    S.PLANNED: (S.PENDING, S.CANCELLED),
    S.PENDING: (S.IN_PROGRESS, S.BLOCKED, S.CANCELLED),
    S.IN_PROGRESS: (S.BLOCKED, S.IN_VALIDATION, S.CANCELLED),
    S.BLOCKED: (S.PENDING, S.IN_PROGRESS, S.CANCELLED),
    S.IN_VALIDATION: (S.DONE, S.IN_PROGRESS, S.CANCELLED),
    S.DONE: (),
    S.CANCELLED: (),
}

# (id, status, required) de uma dependência ou subtarefa
State = tuple[str, str, bool]


def unmet_required(states: Iterable[State]) -> list[str]:
    return [i for i, status, required in states if required and status != S.DONE]


def is_ready(status: str, dependencies: Iterable[State]) -> bool:
    """Pronta para execução: pendente e com todas as dependências obrigatórias concluídas."""
    return status == S.PENDING and not unmet_required(dependencies)


def check_transition(old: str, new: str, dependencies: Iterable[State] = (), subtasks: Iterable[State] = ()) -> None:
    if new not in S.ALL:
        raise TaskRuleError(f"status desconhecido: {new}")
    if new not in TRANSITIONS.get(old, ()):
        raise TaskRuleError(f"transição inválida: {old} -> {new}")
    if new == S.IN_PROGRESS:
        pending = unmet_required(dependencies)
        if pending:
            raise TaskRuleError(f"dependências obrigatórias pendentes: {', '.join(pending)}")
    if new == S.DONE:
        pending = unmet_required(subtasks)
        if pending:
            raise TaskRuleError(f"subtarefas obrigatórias pendentes: {', '.join(pending)}")


def would_cycle(task_id: str, depends_on_id: str, edges: dict[str, set[str]]) -> bool:
    """True se `task_id` depender de `depends_on_id` criaria ciclo (edges: tarefa -> suas dependências)."""
    if task_id == depends_on_id:
        return True
    seen, stack = set(), [depends_on_id]
    while stack:
        cur = stack.pop()
        if cur == task_id:
            return True
        if cur not in seen:
            seen.add(cur)
            stack.extend(edges.get(cur, ()))
    return False


def validate_fields(title: str, priority: str, assignee_kind: str | None, assignee_id: str | None,
                    start_date: str | None, due_date: str | None) -> None:
    if not title or not title.strip() or len(title) > 200:
        raise TaskRuleError("título é obrigatório e tem até 200 caracteres")
    if priority not in Priority.ALL:
        raise TaskRuleError(f"prioridade inválida: {priority}")
    if (assignee_kind is None) != (assignee_id is None):
        raise TaskRuleError("responsável exige tipo e identificador juntos")
    if assignee_kind is not None:
        if assignee_kind not in AssigneeKind.ALL:
            raise TaskRuleError(f"tipo de responsável inválido: {assignee_kind}")
        if not assignee_id.strip() or len(assignee_id) > 100:
            raise TaskRuleError("identificador do responsável é obrigatório e tem até 100 caracteres")
    parsed = []
    for name, value in (("start_date", start_date), ("due_date", due_date)):
        if value is None:
            parsed.append(None)
            continue
        try:
            parsed.append(date.fromisoformat(value))
        except ValueError:
            raise TaskRuleError(f"{name} deve ser AAAA-MM-DD") from None
    if parsed[0] and parsed[1] and parsed[1] < parsed[0]:
        raise TaskRuleError("due_date não pode ser anterior a start_date")
