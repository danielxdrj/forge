import threading

import pytest

from forge_core.agents import AgentOutcome, AgentRegistry, AgentSpec, EchoAgent, Orchestrator, default_registry
from forge_core.config import load_settings
from forge_core.errors import (AgentFailure, ApprovalError, AutomationDisabledError, DispatchRefusedError)
from forge_core.queue import SqlJobQueue
from forge_core.tasks import TaskService, TaskStatus as S


def spec(name="spy", perms=("read",), **kw):
    return AgentSpec(name=name, responsibility="r", scope="s", tools=(), permissions=perms, execution="e", **kw)


class Fake:
    def __init__(self, sp, fn=None):
        self.spec, self.calls, self._fn = sp, 0, fn or (lambda ctx: AgentOutcome(summary="ok"))

    def run(self, ctx):
        self.calls += 1
        return self._fn(ctx)


@pytest.fixture
def env(make_repo):
    repo = make_repo()
    reg = default_registry()
    return repo, TaskService(repo), reg, lambda **kw: Orchestrator(repo, reg, **kw)


def agent_task(svc, name="echo", **kw):
    return svc.create_task("Tarefa", "pessoa:ana", objective="faça", assignee_kind="agent", assignee_id=name, **kw)


def runs(repo):
    return repo.fetch("SELECT agent, status, summary, logs, usage, cost, error FROM agent_runs ORDER BY started_at")


def actions(repo):
    return [(a.action, a.result) for a in repo.list_audit()]


def test_echo_dispatch_result_in_history(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    res = mk().dispatch(t.id)
    assert res.run_status == "success" and res.task_status == S.IN_VALIDATION and res.outcome.cost == 0.0
    row = runs(repo)[0]
    assert row[0] == "echo" and row[1] == "success" and "Tarefa | faça" in row[2] and row[5] == 0.0
    assert "echo recebeu" in row[3] and "input_chars" in row[4]
    changes = [(c.field, c.new_value) for c in svc.changes(t.id)]
    assert ("status", "in_progress") in changes and ("status", "in_validation") in changes
    assert any(f == "agent_run" and v.endswith(":success") for f, v in changes)
    acts = [a for a, _ in actions(repo)]
    assert acts.index("agent.dispatch") < acts.index("agent.result")
    assert "Tarefa | faça" not in repr(repo.list_audit())  # o resumo não vai para a auditoria


def test_dependency_pending_is_not_dispatched(env):
    repo, svc, reg, mk = env
    spy = Fake(spec())
    reg.register(spy)
    dep = svc.create_task("dep", "p")
    t = agent_task(svc, "spy")
    svc.add_dependency(t.id, dep.id, "p")
    with pytest.raises(DispatchRefusedError, match="dependências obrigatórias"):
        mk().dispatch(t.id)
    assert spy.calls == 0 and svc.get_task(t.id).status == "pending" and runs(repo) == []
    assert repo.list_audit()[-1].result.startswith("error")


@pytest.mark.parametrize("setup", ["planned", "no_agent", "person", "unregistered"])
def test_other_refusals(env, setup):
    repo, svc, reg, mk = env
    kw = {}
    if setup == "planned":
        t = agent_task(svc, status=S.PLANNED)
    elif setup == "no_agent":
        t = svc.create_task("t", "p")
    elif setup == "person":
        t = svc.create_task("t", "p", assignee_kind="person", assignee_id="ana")
    else:
        t = agent_task(svc, "fantasma")
    before = svc.get_task(t.id)
    with pytest.raises(DispatchRefusedError):
        mk().dispatch(t.id)
    assert svc.get_task(t.id) == before and runs(repo) == []
    assert repo.list_audit()[-1].action == "agent.dispatch"


def test_new_agent_registered_without_changing_orchestrator(env):
    repo, svc, reg, mk = env
    reg.register(Fake(spec("upper"), lambda ctx: AgentOutcome(summary=ctx.task.title.upper())))
    t = agent_task(svc, "upper")
    assert mk().dispatch(t.id).outcome.summary == "TAREFA"


@pytest.mark.parametrize("perms", [("write",), ("critical",), ("deploy",)])
def test_privileged_without_approval_is_refused_and_audited(make_repo, perms):
    repo = make_repo()
    svc = TaskService(repo)
    fake = Fake(spec("priv", perms))
    reg = AgentRegistry(allow_privileged=True)  # só testes; o registro padrão recusa
    reg.register(fake)
    orch = Orchestrator(repo, reg)
    t = agent_task(svc, "priv")
    before = svc.get_task(t.id)
    with pytest.raises(DispatchRefusedError, match="aprovação pendente"):
        orch.dispatch(t.id)
    assert fake.calls == 0 and svc.get_task(t.id) == before and runs(repo) == []
    last = repo.list_audit()[-1]
    assert (last.action, last.target) == ("agent.dispatch", f"task:{t.id}") and last.result.startswith("error: aprovação")


def test_privileged_with_approval_dispatches_once(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    fake = Fake(spec("priv", ("write", "critical")))
    reg = AgentRegistry(allow_privileged=True)
    reg.register(fake)
    orch = Orchestrator(repo, reg)
    t = agent_task(svc, "priv")
    orch.grant_approval(t.id, "pessoa:chefe")
    res = orch.dispatch(t.id)
    assert res.run_status == "success" and fake.calls == 1
    acts = [a for a, _ in actions(repo)]
    assert "approval.granted" in acts and "approval.consumed" in acts
    # aprovação é de uso único: volta a pending e tenta de novo -> recusado
    svc.change_status(t.id, S.IN_PROGRESS, "p")  # in_validation -> in_progress
    svc.change_status(t.id, S.BLOCKED, "p")
    svc.change_status(t.id, S.PENDING, "p")
    with pytest.raises(DispatchRefusedError, match="aprovação pendente"):
        orch.dispatch(t.id)


def test_approval_must_come_from_a_person_and_for_that_agent(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    reg = AgentRegistry(allow_privileged=True)
    reg.register(Fake(spec("priv", ("write",))))
    orch = Orchestrator(repo, reg)
    t = agent_task(svc, "priv")
    with pytest.raises(ApprovalError):
        orch.grant_approval(t.id, "agente:priv")
    assert repo.list_audit()[-1].result.startswith("error")
    orch.grant_approval(t.id, "pessoa:chefe", agent="outro-agente")  # aprovação para outro agente não vale
    with pytest.raises(DispatchRefusedError):
        orch.dispatch(t.id)
    # linha forjada com ator que não é pessoa também não vale
    repo.record_audit("agente:priv", "approval.granted", f"task:{t.id}", "ok: agent=priv")
    with pytest.raises(DispatchRefusedError):
        orch.dispatch(t.id)


def test_disabled_agent_and_flag(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    off = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AGENTS_DISABLED": "echo"})
    with pytest.raises(DispatchRefusedError, match="desativado"):
        mk(settings=off).dispatch(t.id)
    reg.register(Fake(spec("inativo", active=False)))
    t2 = agent_task(svc, "inativo")
    with pytest.raises(DispatchRefusedError, match="desativado"):
        mk().dispatch(t2.id)


def test_automation_disabled_blocks_dispatch(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    off = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AUTOMATION_ENABLED": "false"})
    with pytest.raises(AutomationDisabledError):
        mk(settings=off).dispatch(t.id)
    assert svc.get_task(t.id).status == "pending" and runs(repo) == []


def test_timeout_cancel_error_and_failure_block_the_task(env):
    repo, svc, reg, mk = env

    def hang(ctx):
        ctx.cancel_event.wait(5)
        return AgentOutcome()

    def boom(ctx):
        raise ValueError(f"PAYLOADSENTINEL {ctx.task.objective}")

    reg.register(Fake(spec("lento", timeout_seconds=0.2), hang))
    reg.register(Fake(spec("quebra"), boom))
    reg.register(Fake(spec("falha"), lambda c: AgentOutcome(status="failure", summary="não deu")))
    reg.register(Fake(spec("espera"), hang))
    expected = {"lento": "timeout", "quebra": "error", "falha": "failure"}
    for name, status in expected.items():
        t = agent_task(svc, name)
        res = mk().dispatch(t.id)
        assert res.run_status == status and res.task_status == S.BLOCKED
    t = agent_task(svc, "espera")
    ev = threading.Event()
    threading.Timer(0.1, ev.set).start()
    assert mk().dispatch(t.id, cancel_event=ev).run_status == "cancelled"
    dump = repr(runs(repo)) + repr(repo.list_audit())
    assert "PAYLOADSENTINEL" not in dump and ("quebra", "error") in [(r[0], r[1]) for r in runs(repo)]
    assert any(r[6] == "ValueError" for r in runs(repo))


def test_secrets_in_logs_usage_and_summary_are_masked(env):
    repo, svc, reg, mk = env

    def fn(ctx):
        ctx.log("chamou com Authorization: Bearer seg redo")
        return AgentOutcome(summary="resultado Bearer abc def", usage={"nota": "Bearer uvw xyz", "n": 3}, cost=0.5)

    reg.register(Fake(spec("vaza"), fn))
    mk().dispatch(agent_task(svc, "vaza").id)
    dump = repr(runs(repo)) + repr(repo.list_audit())
    for s in ("seg", "redo", "abc", "def", "uvw", "xyz"):
        assert s not in dump
    assert '"n": 3' in runs(repo)[0][4]  # usage continua JSON válido


def test_propose_split_creates_nothing_and_apply_needs_a_person(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    orch = mk()
    titles = orch.propose_split(t.id)
    assert len(titles) == 3 and svc.subtasks(t.id) == []
    assert repo.list_audit()[-1].action == "orchestrator.split_proposed"
    with pytest.raises(ApprovalError):
        orch.apply_split(t.id, titles, "agente:orchestrator")
    assert svc.subtasks(t.id) == []
    created = orch.apply_split(t.id, titles, "pessoa:ana")
    assert len(created) == 3 and len(svc.subtasks(t.id)) == 3


def test_job_handler_and_idempotent_enqueue(env):
    repo, svc, reg, mk = env
    orch = mk()
    q = SqlJobQueue(repo)
    t = agent_task(svc)
    j1, j2 = orch.enqueue(q, t.id, "pessoa:ana"), orch.enqueue(q, t.id, "pessoa:ana")
    assert j1.id == j2.id
    job = q.run_once(orch.handler() if hasattr(orch, "handler") else orch.job_handler(), "agente:worker")
    assert job.status == "succeeded" and svc.get_task(t.id).status == S.IN_VALIDATION
    # tarefa não pronta: recusa vira falha definitiva do job, sem retry
    bad = svc.create_task("sem agente", "p")
    orch.enqueue(q, bad.id, "pessoa:ana")
    assert q.run_once(orch.job_handler(), "agente:worker").status == "failed"


def test_agent_runs_append_only_sqlite(tmp_path):
    import sqlite3

    from forge_core.storage import open_repository

    repo = open_repository(f"sqlite:///{tmp_path / 'r.db'}")
    svc = TaskService(repo)
    Orchestrator(repo, default_registry()).dispatch(agent_task(svc).id)
    for sql in ("UPDATE agent_runs SET status = 'x'", "DELETE FROM agent_runs"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            repo._conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE agent_runs SET status = 'x'", "DELETE FROM agent_runs", "TRUNCATE agent_runs"])
def test_agent_runs_append_only_and_privileges_postgres(pg_env, sql):
    import psycopg

    writer, owner, _ = pg_env
    Orchestrator(writer, default_registry()).dispatch(agent_task(TaskService(writer)).id)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner._run([(sql, ())])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])
