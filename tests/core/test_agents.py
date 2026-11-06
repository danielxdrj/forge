import threading

import pytest

from forge_core.agents import AgentContext, AgentOutcome, AgentRegistry, AgentRuntime, AgentSpec, EchoAgent, default_registry
from forge_core.config import load_settings
from forge_core.errors import AgentError, AgentFailure
from forge_core.tasks.model import Task


def spec(**kw):
    base = dict(name="x-agent", responsibility="r", scope="s", tools=(), permissions=("read",), execution="e")
    return AgentSpec(**{**base, **kw})


def task():
    return Task("t1", "titulo", "obj", "", "", "", "normal", "pending", "agent", "x-agent", None, None, None,
                None, None, True, 1, "now", "now")


class Fake:
    def __init__(self, sp, fn=None):
        self.spec, self._fn = sp, fn or (lambda ctx: AgentOutcome(summary="ok"))

    def run(self, ctx):
        return self._fn(ctx)


@pytest.mark.parametrize("kw", [{"name": "Maiusculo"}, {"name": "x"}, {"responsibility": " "}, {"scope": ""},
                                {"execution": ""}, {"timeout_seconds": 0}])
def test_invalid_spec(kw):
    with pytest.raises(AgentError):
        spec(**kw)


@pytest.mark.parametrize("perms, needs", [(("read",), False), (("read", "write"), True), (("critical",), True),
                                          (("deploy",), True), ((), True)])
def test_requires_approval_unknown_permission_needs_approval(perms, needs):
    assert spec(permissions=perms).requires_approval is needs


def test_registry_default_has_only_echo_and_always_refuses_privileged():
    reg = default_registry()
    assert reg.names() == ["echo"]
    for perms in (("write",), ("critical",), ("read", "write"), ("deploy",), ()):
        with pytest.raises(AgentError, match="privileged agents disabled until approver authentication"):
            reg.register(Fake(spec(permissions=perms)))
    assert reg.names() == ["echo"]
    import inspect

    assert not inspect.signature(AgentRegistry.__init__).parameters.keys() - {"self"}  # nenhum flag


@pytest.mark.parametrize("perms", [("write",), ("critical",), ("deploy",), ()])
def test_runtime_refuses_privileged_even_when_called_directly(perms):
    called = []
    agent = Fake(spec(permissions=perms), lambda c: called.append(1) or AgentOutcome())
    with pytest.raises(AgentError, match="privileged agents disabled"):
        AgentRuntime().execute(agent, AgentContext(task(), "a"))
    assert called == []


def test_runtime_honors_automation_flag_and_disabled_agents_from_environment(monkeypatch):
    from forge_core.errors import AutomationDisabledError

    agent = Fake(spec())
    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "false")
    with pytest.raises(AutomationDisabledError):
        AgentRuntime().execute(agent, AgentContext(task(), "a"))
    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("FORGE_AGENTS_DISABLED", "x-agent")
    with pytest.raises(AgentError, match="desativado"):
        AgentRuntime().execute(agent, AgentContext(task(), "a"))
    monkeypatch.delenv("FORGE_AGENTS_DISABLED")
    assert AgentRuntime().execute(agent, AgentContext(task(), "a")).status == "success"


def test_context_is_sealed_after_timeout_and_late_result_is_dropped():
    late_done = threading.Event()
    release = threading.Event()

    def fn(ctx):
        ctx.cancel_event.wait(5)
        release.wait(5)
        ctx.log("EFEITO-TARDIO")
        late_done.set()
        return AgentOutcome(summary="tardio", artifacts=["a"], usage={"n": 1})

    ctx = AgentContext(task(), "a")
    res = AgentRuntime().execute(Fake(spec(timeout_seconds=0.2), fn), ctx)
    assert res.status == "timeout" and ctx.sealed
    release.set()
    assert late_done.wait(2)
    assert ctx.logs == [] and res.logs == [] and res.outcome is None


def test_registry_new_agent_and_duplicates():
    reg = AgentRegistry()
    reg.register(EchoAgent())
    reg.register(Fake(spec()))
    assert reg.names() == ["echo", "x-agent"]
    with pytest.raises(AgentError, match="já registrado"):
        reg.register(EchoAgent())


def test_runtime_success_and_log_redaction():
    def fn(ctx):
        ctx.log("Authorization: Bearer seg redo")
        return AgentOutcome(summary="ok", usage={"n": 1})

    ctx = AgentContext(task(), "agente:x-agent")
    res = AgentRuntime().execute(Fake(spec(), fn), ctx)
    assert res.status == "success" and res.outcome.summary == "ok"
    assert "seg" not in repr(res.logs) and "redo" not in repr(res.logs)


def test_runtime_failure_outcome():
    res = AgentRuntime().execute(Fake(spec(), lambda c: AgentOutcome(status="failure", summary="não deu")),
                                 AgentContext(task(), "a"))
    assert res.status == "failure"


def test_runtime_error_records_only_type():
    def fn(ctx):
        raise ValueError("PAYLOADSENTINEL")

    res = AgentRuntime().execute(Fake(spec(), fn), AgentContext(task(), "a"))
    assert res.status == "error" and res.error == "ValueError" and "PAYLOADSENTINEL" not in repr(res)


def test_runtime_explicit_agent_failure_is_redacted():
    def fn(ctx):
        raise AgentFailure("API recusou: Authorization: Bearer seg redo")

    res = AgentRuntime().execute(Fake(spec(), fn), AgentContext(task(), "a"))
    assert res.error.startswith("AgentFailure:") and "seg" not in res.error and "redo" not in res.error


def test_runtime_invalid_outcome():
    res = AgentRuntime().execute(Fake(spec(), lambda c: "texto"), AgentContext(task(), "a"))
    assert res.status == "error" and res.error == "InvalidOutcome"


def test_runtime_timeout_signals_cancel_and_returns():
    seen = threading.Event()

    def fn(ctx):
        ctx.cancel_event.wait(5)
        seen.set()
        return AgentOutcome()

    ctx = AgentContext(task(), "a")
    res = AgentRuntime().execute(Fake(spec(timeout_seconds=0.2), fn), ctx)
    assert res.status == "timeout" and ctx.cancel_event.is_set()
    assert seen.wait(2)  # o agente cooperativo percebeu o sinal


def test_runtime_external_cancel():
    ctx = AgentContext(task(), "a")
    threading.Timer(0.1, ctx.cancel_event.set).start()
    res = AgentRuntime().execute(Fake(spec(), lambda c: (c.cancel_event.wait(5), AgentOutcome())[1]), ctx)
    assert res.status == "cancelled"


def test_agents_disabled_setting_parsing():
    s = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AGENTS_DISABLED": " Echo, outro ,"})
    assert s.agents_disabled == ("echo", "outro")
    assert load_settings({"FORGE_CONFIG_DIR": "x"}).agents_disabled == ()
