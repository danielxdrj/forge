import threading

import pytest

from auth_helpers import actor
from forge_core.agents import AgentOutcome, AgentRegistry, AgentSpec, EchoAgent, Orchestrator, default_registry
from inprocess_runtime import InProcessRuntime as AgentRuntime
from forge_core.agents.approval import ALLOW, DISABLED, NEEDS_APPROVAL, decide
from forge_core.config import load_settings
from forge_core.errors import (AgentError, AgentFailure, ApprovalError, AuthenticationError, AutomationDisabledError, DispatchRefusedError)
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
    return svc.create_task("Tarefa", actor(svc, "ana"), objective="faça", assignee_kind="agent", assignee_id=name, **kw)


def runs(repo):
    return repo.fetch("SELECT agent, status, summary, logs, usage, cost, error FROM agent_runs ORDER BY started_at")


def actions(repo):
    return [(a.action, a.result) for a in repo.list_audit()]


def test_echo_dispatch_result_in_history(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    res = mk().dispatch(t.id, actor(repo, "ana"))
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
    dep = svc.create_task("dep", actor(svc, "ana"))
    t = agent_task(svc, "spy")
    svc.add_dependency(t.id, dep.id, actor(svc, "ana"))
    with pytest.raises(DispatchRefusedError, match="dependências obrigatórias"):
        mk().dispatch(t.id, actor(repo, "ana"))
    assert spy.calls == 0 and svc.get_task(t.id).status == "pending" and runs(repo) == []
    assert repo.list_audit()[-1].result.startswith("error")


@pytest.mark.parametrize("setup", ["planned", "no_agent", "person", "unregistered"])
def test_other_refusals(env, setup):
    repo, svc, reg, mk = env
    kw = {}
    if setup == "planned":
        t = agent_task(svc, status=S.PLANNED)
    elif setup == "no_agent":
        t = svc.create_task("t", actor(svc, "ana"))
    elif setup == "person":
        t = svc.create_task("t", actor(svc, "ana"), assignee_kind="person", assignee_id="ana")
    else:
        t = agent_task(svc, "fantasma")
    before = svc.get_task(t.id)
    with pytest.raises(DispatchRefusedError):
        mk().dispatch(t.id, actor(repo, "ana"))
    assert svc.get_task(t.id) == before and runs(repo) == []
    assert repo.list_audit()[-1].action == "agent.dispatch"


def test_new_agent_registered_without_changing_orchestrator(env):
    repo, svc, reg, mk = env
    reg.register(Fake(spec("upper"), lambda ctx: AgentOutcome(summary=ctx.task.title.upper())))
    t = agent_task(svc, "upper")
    assert mk().dispatch(t.id, actor(repo, "ana")).outcome.summary == "TAREFA"


def privileged_env(make_repo, name="priv", perms=("write",)):
    """Registra o agente privilegiado FALSO pelo dicionário interno: o registro público o recusa sempre."""
    repo = make_repo()
    svc = TaskService(repo)
    fake = Fake(spec(name, perms))
    reg = AgentRegistry()
    with pytest.raises(AgentError):
        reg.register(fake)
    reg._agents[name] = fake  # só teste: prova a defesa em profundidade do Orchestrator
    return repo, svc, fake, Orchestrator(repo, reg)


PRIV = "privileged agents disabled until approver authentication"


@pytest.mark.parametrize("perms", [("write",), ("critical",), ("deploy",)])
def test_privileged_without_approval_is_refused_and_audited(make_repo, perms):
    repo, svc, fake, orch = privileged_env(make_repo, perms=perms)
    t = agent_task(svc, "priv")
    before = svc.get_task(t.id)
    with pytest.raises(DispatchRefusedError, match="aprovação pendente"):
        orch.dispatch(t.id, actor(repo, "ana"))
    assert fake.calls == 0 and svc.get_task(t.id) == before and runs(repo) == []
    last = repo.list_audit()[-1]
    assert (last.action, last.target) == ("agent.dispatch", f"task:{t.id}") and last.result.startswith("error: aprovação")


@pytest.mark.parametrize("perms", [("write",), ("critical",), ("read", "write"), ("deploy",)])
def test_privileged_with_approval_granted_still_does_not_execute(make_repo, perms):
    repo, svc, fake, orch = privileged_env(make_repo, perms=perms)
    t = agent_task(svc, "priv")
    before = svc.get_task(t.id)
    orch.grant_approval(t.id, actor(repo, "chefe"))  # aprovador verificado: registra, mas não libera nada
    assert any(a == "approval.granted" and r.startswith("ok: agent=priv") for a, r in actions(repo))
    with pytest.raises(DispatchRefusedError, match=PRIV):
        orch.dispatch(t.id, actor(repo, "ana"))
    assert fake.calls == 0 and svc.get_task(t.id) == before and runs(repo) == []
    last = repo.list_audit()[-1]
    assert last.action == "agent.dispatch" and last.result == f"error: {PRIV}"
    assert "approval.consumed" not in [a for a, _ in actions(repo)]  # nada foi reservado


def test_text_approver_is_refused_and_grants_nothing(make_repo):
    repo, svc, fake, orch = privileged_env(make_repo, perms=("write",))
    t = agent_task(svc, "priv")
    with pytest.raises(ApprovalError, match="principal_missing"):
        orch.grant_approval(t.id, "pessoa:forjada")
    with pytest.raises(DispatchRefusedError, match="aprovação pendente"):
        orch.dispatch(t.id, actor(repo, "ana"))
    assert fake.calls == 0


def test_policy_function_never_allows_privileged():
    for perms in (("write",), ("critical",), ("deploy",), ()):
        assert decide(spec(perms=perms), approved=False) == NEEDS_APPROVAL
        assert decide(spec(perms=perms), approved=True) == DISABLED
    assert decide(spec(), approved=False) == ALLOW


def test_approval_must_come_from_a_person_and_for_that_agent(make_repo):
    repo, svc, fake, orch = privileged_env(make_repo, perms=("write",))
    t = agent_task(svc, "priv")
    with pytest.raises(ApprovalError):
        orch.grant_approval(t.id, "agente:priv")
    assert repo.list_audit()[-1].result.startswith("error")
    orch.grant_approval(t.id, actor(repo, "chefe"), agent="outro-agente")  # aprovação de outro agente não conta
    with pytest.raises(DispatchRefusedError, match="aprovação pendente"):
        orch.dispatch(t.id, actor(repo, "ana"))
    repo.record_audit("agente:priv", "approval.granted", f"task:{t.id}", "ok: agent=priv")  # linha forjada
    with pytest.raises(DispatchRefusedError, match="aprovação pendente"):
        orch.dispatch(t.id, actor(repo, "ana"))
    assert fake.calls == 0


def test_disabled_agent_and_flag(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    off = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AGENTS_DISABLED": "echo"})
    with pytest.raises(DispatchRefusedError, match="desativado"):
        mk(settings=off).dispatch(t.id, actor(repo, "ana"))
    reg.register(Fake(spec("inativo", active=False)))
    t2 = agent_task(svc, "inativo")
    with pytest.raises(DispatchRefusedError, match="desativado"):
        mk().dispatch(t2.id, actor(repo, "ana"))


def test_automation_disabled_blocks_dispatch(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    off = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AUTOMATION_ENABLED": "false"})
    with pytest.raises(AutomationDisabledError):
        mk(settings=off).dispatch(t.id, actor(repo, "ana"))
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
        res = mk().dispatch(t.id, actor(repo, "ana"))
        assert res.run_status == status and res.task_status == S.BLOCKED
    t = agent_task(svc, "espera")
    ev = threading.Event()
    threading.Timer(0.1, ev.set).start()
    assert mk().dispatch(t.id, actor(repo, "ana"), cancel_event=ev).run_status == "cancelled"
    dump = repr(runs(repo)) + repr(repo.list_audit())
    assert "PAYLOADSENTINEL" not in dump and ("quebra", "error") in [(r[0], r[1]) for r in runs(repo)]
    assert any(r[6] == "ValueError" for r in runs(repo))


def test_secrets_in_logs_usage_and_summary_are_masked(env):
    repo, svc, reg, mk = env

    def fn(ctx):
        ctx.log("chamou com Authorization: Bearer seg redo")
        return AgentOutcome(summary="resultado Bearer abc def", usage={"nota": "Bearer uvw xyz", "n": 3}, cost=0.5)

    reg.register(Fake(spec("vaza"), fn))
    mk().dispatch(agent_task(svc, "vaza").id, actor(repo, "ana"))
    dump = repr(runs(repo)) + repr(repo.list_audit())
    for s in ("seg redo", "abc def", "uvw xyz"):
        assert s not in dump
    assert '"n": 3' in runs(repo)[0][4]  # usage continua JSON válido


def test_propose_split_creates_nothing_and_apply_needs_a_person(env):
    repo, svc, reg, mk = env
    t = agent_task(svc)
    orch = mk()
    titles = orch.propose_split(t.id)
    assert len(titles) == 3 and svc.subtasks(t.id) == []
    assert repo.list_audit()[-1].action == "orchestrator.split_proposed"
    with pytest.raises((ApprovalError, AuthenticationError)):
        orch.apply_split(t.id, titles, "agente:orchestrator")
    assert svc.subtasks(t.id) == []
    created = orch.apply_split(t.id, titles, actor(repo, "ana"))
    assert len(created) == 3 and len(svc.subtasks(t.id)) == 3


def test_no_unattended_dispatch_path_without_a_service_identity(env):
    repo, svc, reg, mk = env
    orch = mk()
    assert not hasattr(orch, "enqueue") and not hasattr(orch, "job_handler") and not hasattr(orch, "handler")
    t = agent_task(svc)
    with pytest.raises(AuthenticationError, match="principal_missing"):
        orch.dispatch(t.id, "sistema:fila")
    with pytest.raises(AuthenticationError, match="principal_missing"):
        orch.dispatch(t.id, None)
    assert svc.get_task(t.id).status == S.PENDING and runs(repo) == []


def test_agent_runs_append_only_sqlite(tmp_path):
    import sqlite3

    from forge_core.storage import open_repository

    repo = open_repository(f"sqlite:///{tmp_path / 'r.db'}")
    svc = TaskService(repo)
    Orchestrator(repo, default_registry()).dispatch(agent_task(svc).id, actor(repo, "ana"))
    for sql in ("UPDATE agent_runs SET status = 'x'", "DELETE FROM agent_runs"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            repo._conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE agent_runs SET status = 'x'", "DELETE FROM agent_runs", "TRUNCATE agent_runs"])
def test_agent_runs_append_only_and_privileges_postgres(pg_env, sql):
    import psycopg

    writer, owner, _ = pg_env
    Orchestrator(writer, default_registry()).dispatch(agent_task(TaskService(writer)).id, actor(writer, "ana"))
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner._run([(sql, ())])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])


def test_settings_none_reads_environment_for_dispatch_and_runtime(env, monkeypatch):
    repo, svc, reg, mk = env
    orch = mk()  # settings=None
    t = agent_task(svc)
    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "false")
    with pytest.raises(AutomationDisabledError):
        orch.dispatch(t.id, actor(repo, "ana"))
    with pytest.raises(AutomationDisabledError):
        AgentRuntime().check_allowed(EchoAgent())
    assert svc.get_task(t.id).status == "pending" and runs(repo) == []
    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("FORGE_AGENTS_DISABLED", "echo")
    with pytest.raises(DispatchRefusedError, match="desativado"):
        orch.dispatch(t.id, actor(repo, "ana"))
    monkeypatch.delenv("FORGE_AGENTS_DISABLED")
    assert orch.dispatch(t.id, actor(repo, "ana")).run_status == "success"


def test_invalid_environment_fails_closed(env, monkeypatch):
    from forge_core.errors import ConfigError

    repo, svc, reg, mk = env
    t = agent_task(svc)
    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "talvez")
    with pytest.raises(ConfigError):
        mk().dispatch(t.id, actor(repo, "ana"))
    assert svc.get_task(t.id).status == "pending"


def test_late_effects_after_timeout_write_nothing(env):
    repo, svc, reg, mk = env
    release, done = threading.Event(), threading.Event()

    def late(ctx):
        ctx.cancel_event.wait(5)
        release.wait(5)
        ctx.log("EFEITO-TARDIO")
        done.set()
        return AgentOutcome(summary="EFEITO-TARDIO", artifacts=["EFEITO-TARDIO"], usage={"n": 1})

    reg.register(Fake(spec("tardio", timeout_seconds=0.2), late))
    t = agent_task(svc, "tardio")
    res = mk().dispatch(t.id, actor(repo, "ana"))
    assert res.run_status == "timeout" and res.task_status == S.BLOCKED

    def snapshot():
        return (repo.fetch("SELECT COUNT(*) FROM agent_runs")[0][0], repo.fetch("SELECT COUNT(*) FROM task_changes")[0][0],
                repo.fetch("SELECT COUNT(*) FROM audit_log")[0][0])

    before = snapshot()
    release.set()
    assert done.wait(2)
    import time

    time.sleep(0.2)
    assert snapshot() == before
    assert "EFEITO-TARDIO" not in repr(runs(repo)) + repr(repo.list_audit())
