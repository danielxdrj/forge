import pytest

from forge_core.errors import TaskRuleError
from forge_core.tasks import TRANSITIONS, TaskStatus as S, is_ready
from forge_core.tasks.rules import check_transition, validate_fields, would_cycle

OK = dict(title="t", priority="normal", assignee_kind=None, assignee_id=None, start_date=None, due_date=None)


@pytest.mark.parametrize("old", S.ALL)
@pytest.mark.parametrize("new", S.ALL)
def test_transition_table_is_enforced(old, new):
    if new in TRANSITIONS[old]:
        check_transition(old, new)
    else:
        with pytest.raises(TaskRuleError, match="transição inválida"):
            check_transition(old, new)


def test_terminal_states_have_no_exit():
    assert TRANSITIONS[S.DONE] == () and TRANSITIONS[S.CANCELLED] == ()


def test_required_dependency_pending_blocks_start():
    with pytest.raises(TaskRuleError, match="dependências obrigatórias"):
        check_transition(S.PENDING, S.IN_PROGRESS, dependencies=[("a", S.IN_PROGRESS, True)])
    with pytest.raises(TaskRuleError):
        check_transition(S.BLOCKED, S.IN_PROGRESS, dependencies=[("a", S.CANCELLED, True)])


def test_optional_dependency_does_not_block():
    check_transition(S.PENDING, S.IN_PROGRESS, dependencies=[("a", S.PENDING, False), ("b", S.DONE, True)])


def test_is_ready_requires_pending_and_done_required_deps():
    assert is_ready(S.PENDING, [("a", S.DONE, True), ("b", S.PLANNED, False)])
    assert not is_ready(S.PENDING, [("a", S.PENDING, True)])
    assert not is_ready(S.PLANNED, [])
    assert not is_ready(S.IN_PROGRESS, [])


def test_required_subtask_pending_blocks_completion():
    with pytest.raises(TaskRuleError, match="subtarefas obrigatórias"):
        check_transition(S.IN_VALIDATION, S.DONE, subtasks=[("s", S.IN_PROGRESS, True)])
    with pytest.raises(TaskRuleError):
        check_transition(S.IN_VALIDATION, S.DONE, subtasks=[("s", S.CANCELLED, True)])


def test_optional_subtask_does_not_block_completion():
    check_transition(S.IN_VALIDATION, S.DONE, subtasks=[("s", S.PENDING, False), ("t", S.DONE, True)])


def test_cannot_complete_without_validation():
    with pytest.raises(TaskRuleError):
        check_transition(S.IN_PROGRESS, S.DONE)


def test_cycles_and_self_dependency():
    edges = {"b": {"a"}, "c": {"b"}}  # c -> b -> a
    assert would_cycle("a", "c", edges)
    assert would_cycle("a", "a", {})
    assert not would_cycle("c", "a", edges)


@pytest.mark.parametrize(
    "override",
    [
        {"title": " "}, {"title": "x" * 201}, {"priority": "enorme"}, {"assignee_kind": "person"},
        {"assignee_kind": "robo", "assignee_id": "x"}, {"assignee_kind": "agent", "assignee_id": " "},
        {"start_date": "01/02/2026"}, {"start_date": "2026-02-10", "due_date": "2026-02-01"},
    ],
)
def test_invalid_fields(override):
    with pytest.raises(TaskRuleError):
        validate_fields(**{**OK, **override})


def test_valid_fields():
    validate_fields(**{**OK, "assignee_kind": "agent", "assignee_id": "triagem",
                       "start_date": "2026-02-01", "due_date": "2026-02-01"})
