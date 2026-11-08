import threading
"""Testes unitários do executor isolado, sem Docker: protocolo, gates e falha fechada."""
import json

import pytest

from forge_core.agents import AgentOutcome, AgentSpec, Permission
from forge_core.agents.sandbox import IsolatedRuntime, validate_output
from forge_core.agents.spec import AgentContext
from forge_core.config import Settings
from forge_core.errors import AgentError, AutomationDisabledError
from forge_core.tasks.model import Task


def _settings(enabled=True, disabled=frozenset()):
    return Settings(config_dir="cfg.example.invalid", log_level="INFO", automation_enabled=enabled,
                    database_url=None, database_migration_url=None, agents_disabled=frozenset(disabled))


class FakeSandbox:
    def __init__(self, result):
        self.result, self.calls = result, 0

    def run(self, agent, payload, timeout, cancel_event=None):
        self.calls += 1
        return self.result


class Agent:
    def __init__(self, perms=(Permission.READ,)):
        self.spec = AgentSpec(name="agente-teste", responsibility="r", scope="s", tools=(), permissions=perms,
                              execution="e", timeout_seconds=5)

    def run(self, ctx):
        return AgentOutcome()


def _ctx():
    t = Task("t", "titulo", "obj", "", "", "", "normal", "in_progress", None, None, None, None, None, None, None,
             True, 1, "", "")
    return AgentContext(task=t, actor="pessoa:ana")


@pytest.mark.parametrize("raw", [
    b'{"status":"success","summary":"ok"}\n{"status":"success"}\n',
    b'{"status":"success","extra":1}\n',
    b'{"status":"weird"}\n',
    b'["lista"]\n',
    b'{"status":"success","summary":"' + b"x" * 3000 + b'"}\n',
    b'{"status":"success","logs":' + json.dumps(["x" * 301]).encode() + b'}\n',
    b'{"status":"success","logs":' + json.dumps(["x"] * 51).encode() + b'}\n',
    b"nao e json\n",
    b"\xff\xfe\n",
])
def test_protocol_rejects_malformed_or_excessive_output(raw):
    with pytest.raises((ValueError, UnicodeDecodeError, json.JSONDecodeError)):
        validate_output(raw)


def test_protocol_rejects_oversized_output():
    with pytest.raises(ValueError, match="output_too_large"):
        validate_output(b"x" * (64 * 1024 + 1))


def test_protocol_accepts_valid_and_redacts_logs():
    d = validate_output(b'{"status":"success","summary":"ok","logs":["Bearer abcdef123"]}\n')
    assert d["status"] == "success" and "abcdef123" not in d["logs"][0]


def test_runtime_maps_sandbox_results_without_thread_fallback():
    from forge_core.agents.sandbox import SandboxResult

    rt = IsolatedRuntime(FakeSandbox(SandboxResult("success", "ok", ["l"])), settings=_settings())
    res = rt.execute(Agent(), _ctx())
    assert res.status == "success" and res.outcome.summary == "ok" and res.logs == ["l"]
    rt = IsolatedRuntime(FakeSandbox(SandboxResult("timeout", error="timeout")), settings=_settings())
    assert rt.execute(Agent(), _ctx()).status == "timeout"
    rt = IsolatedRuntime(FakeSandbox(SandboxResult("error", error="cleanup_unconfirmed")), settings=_settings())
    res = rt.execute(Agent(), _ctx())
    assert res.status == "error" and res.error == "cleanup_unconfirmed"


def test_runtime_refuses_privileged_and_disabled_before_calling_sandbox():
    from forge_core.agents.sandbox import SandboxResult

    fake = FakeSandbox(SandboxResult("success", "ok"))
    with pytest.raises(AgentError, match="privileged agents disabled"):
        IsolatedRuntime(fake, settings=_settings()).execute(Agent((Permission.WRITE,)), _ctx())
    with pytest.raises(AgentError, match="desativado"):
        IsolatedRuntime(fake, settings=_settings(disabled={"agente-teste"})).execute(Agent(), _ctx())
    assert fake.calls == 0


def test_automation_off_with_settings_none_blocks_isolated_runtime(monkeypatch):
    from forge_core.agents.sandbox import SandboxResult

    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "false")
    fake = FakeSandbox(SandboxResult("success", "ok"))
    with pytest.raises(AutomationDisabledError):
        IsolatedRuntime(fake).execute(Agent(), _ctx())
    assert fake.calls == 0


def test_docker_missing_fails_closed(monkeypatch):
    from forge_core.agents.sandbox import DockerSandbox

    def boom(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr("forge_core.agents.sandbox.subprocess.Popen", boom)
    res = DockerSandbox("img").run(Agent(), {}, 5)
    assert res.status == "error" and res.error == "docker_unavailable"


def test_orchestrator_refuses_any_non_isolated_runtime(tmp_path):
    from forge_core.agents import AgentRegistry, Orchestrator
    from forge_core.storage import open_repository

    with pytest.raises(TypeError, match="runtime isolado"):
        Orchestrator(open_repository(f"sqlite:///{tmp_path / 'x.db'}"), AgentRegistry(), runtime=object())


def test_no_thread_runtime_in_production_api():
    import forge_core.agents as agents
    import forge_core.agents.runtime as runtime_mod

    assert not hasattr(runtime_mod, "AgentRuntime")
    assert "AgentRuntime" not in dir(agents)


def test_isolated_runtime_without_sandbox_refuses_to_run():
    from forge_core.agents.sandbox import IsolatedRuntime

    with pytest.raises(AgentError, match="sem sandbox"):
        IsolatedRuntime(None, settings=_settings()).execute(Agent(), _ctx())


def test_public_dispatch_without_docker_fails_closed_and_never_runs_in_thread(tmp_path, monkeypatch):
    import forge_core.agents.orchestrator as orch_mod
    import forge_core.agents.sandbox as sandbox_mod
    from forge_core.agents import Orchestrator, default_registry
    from forge_core.storage import open_repository
    from forge_core.tasks import TaskService

    monkeypatch.setattr(orch_mod, "default_runtime", sandbox_mod.default_runtime)  # o padrão REAL, sem dublê
    monkeypatch.setenv("PATH", "")  # sem docker
    repo = open_repository(f"sqlite:///{tmp_path / 'd.db'}")
    svc = TaskService(repo)
    t = svc.create_task("tarefa", "pessoa:ana", assignee_kind="agent", assignee_id="echo")
    res = Orchestrator(repo, default_registry(), tasks=svc, settings=_settings()).dispatch(t.id)
    assert res.run_status == "error" and res.error == "docker_unavailable"
    assert res.outcome is None and res.task_status != "in_validation"
    assert svc.get_task(t.id).status != "in_validation"


def test_runtime_passes_usage_and_cost_from_protocol():
    from forge_core.agents.sandbox import SandboxResult

    rt = IsolatedRuntime(FakeSandbox(SandboxResult("success", "ok", usage={"tokens": 3}, cost=0.5)),
                         settings=_settings())
    res = rt.execute(Agent(), _ctx())
    assert res.outcome.usage == {"tokens": 3} and res.outcome.cost == 0.5


def test_protocol_rejects_bad_usage_and_cost():
    for raw in (b'{"status":"success","usage":{"a":"x"}}\n', b'{"status":"success","cost":true}\n'):
        with pytest.raises(ValueError):
            validate_output(raw)


class FakeProc:
    def __init__(self, out=b"", stall=False, returncode=0):
        import io

        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(out)
        self.returncode = returncode
        self._stall = stall
        self.killed = False

    def wait(self, timeout=None):
        import subprocess

        if self._stall:
            raise subprocess.TimeoutExpired("docker", timeout)
        return self.returncode

    def poll(self):
        return None if self._stall and not self.killed else self.returncode

    def kill(self):
        self.killed = True


@pytest.fixture
def fake_docker(monkeypatch):
    import subprocess

    import forge_core.agents.sandbox as sb

    calls = []
    state = {"ps": ("rc", 0, ""), "stall": False, "out": b'{"status":"success","summary":"ok"}\n'}

    def fake_docker_cli(*args):
        calls.append(args)
        if args[0] == "ps":
            kind, rc, out = state["ps"]
            if kind == "raise":
                raise subprocess.TimeoutExpired("docker", 1)
            return subprocess.CompletedProcess(args, rc, out, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    proc = {}

    def fake_popen(*a, **k):
        proc["p"] = FakeProc(out=state["out"], stall=state["stall"])
        return proc["p"]

    monkeypatch.setattr(sb, "_docker", fake_docker_cli)
    monkeypatch.setattr(sb.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sb, "_KILL_GRACE", 0.3)
    return {"calls": calls, "state": state, "proc": proc}


def test_daemon_error_on_inspect_is_not_confirmed_removal(fake_docker):
    from forge_core.agents.sandbox import DockerSandbox

    fake_docker["state"]["ps"] = ("rc", 1, "")  # daemon inacessível: NÃO é prova de ausência
    res = DockerSandbox("img").run(Agent(), {}, 5)
    assert res.status == "error" and res.error == "cleanup_unconfirmed"


def test_timeout_on_inspect_is_not_confirmed_removal(fake_docker):
    from forge_core.agents.sandbox import DockerSandbox

    fake_docker["state"]["ps"] = ("raise", 0, "")
    assert DockerSandbox("img").run(Agent(), {}, 5).error == "cleanup_unconfirmed"


def test_container_still_listed_is_not_confirmed(fake_docker):
    from forge_core.agents.sandbox import DockerSandbox

    fake_docker["state"]["ps"] = ("rc", 0, "abc123\n")
    assert DockerSandbox("img").run(Agent(), {}, 5).error == "cleanup_unconfirmed"


def test_absence_proven_by_empty_listing_is_success(fake_docker):
    from forge_core.agents.sandbox import DockerSandbox

    res = DockerSandbox("img").run(Agent(), {}, 5)
    assert res.status == "success"
    assert any(c[0] == "kill" for c in fake_docker["calls"]) and any(c[0] == "rm" for c in fake_docker["calls"])


def test_stalled_wait_still_destroys_container(fake_docker):
    from forge_core.agents.sandbox import DockerSandbox

    fake_docker["state"]["stall"] = True
    res = DockerSandbox("img").run(Agent(), {}, 5)
    assert res.error == "sandbox_stalled"
    assert fake_docker["proc"]["p"].killed
    assert any(c[0] == "rm" for c in fake_docker["calls"])


def test_exception_in_supervisor_still_destroys_container(fake_docker, monkeypatch):
    import forge_core.agents.sandbox as sb

    monkeypatch.setattr(sb.DockerSandbox, "_collect", staticmethod(lambda *a: 1 / 0))
    res = sb.DockerSandbox("img").run(Agent(), {}, 5)
    assert res.error == "supervisor_failed"
    assert any(c[0] == "rm" for c in fake_docker["calls"])


@pytest.mark.parametrize("error", ["SEGREDO-ghp_" + "A" * 36 + "-X", "Traceback: senha=abc", "x" * 80, "agent_exception "])
def test_child_error_outside_allowlist_is_never_returned(error):
    import json as j

    from forge_core.agents.sandbox import interpret_output

    raw = j.dumps({"status": "error", "error": error}).encode() + b"\n"
    res = interpret_output(raw)
    assert res.error == "invalid_output"
    assert "SEGREDO" not in repr(res) and "senha" not in repr(res)


def test_child_allowlisted_error_passes_through():
    import json as j

    from forge_core.agents.sandbox import interpret_output

    assert interpret_output(j.dumps({"status": "error", "error": "agent_exception"}).encode() + b"\n").error == \
        "agent_exception"


def test_token_shaped_text_in_logs_is_masked():
    import json as j

    from forge_core.agents.sandbox import interpret_output

    token = "ghp_" + "B" * 36
    raw = j.dumps({"status": "success", "logs": [f"uso {token}"]}).encode() + b"\n"
    res = interpret_output(raw)
    assert token not in repr(res) and res.logs == ["uso ***"]


def test_run_args_profile_is_the_only_isolation_definition():
    from forge_core.agents.sandbox import run_args

    args = run_args("n", "img", ("python",))
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL", "--no-new-privileges" if False else
                 "no-new-privileges", "--user", "65532:65532", "--pids-limit", "32", "--memory", "128m"):
        assert flag in args
    assert "-v" not in args and "--volume" not in args and "--privileged" not in args
    assert not any(a.startswith("--mount") or a.startswith("--env") or a == "-e" for a in args)


def _finished_reader():
    reader = threading.Thread(target=lambda: None)
    reader.start()
    reader.join()
    return reader


def test_cancel_observed_after_reader_finished_is_not_success():
    from forge_core.agents.sandbox import DockerSandbox

    ev = threading.Event()
    ev.set()
    box = {"out": b'{"status":"success","summary":"ok"}\n'}
    res = DockerSandbox._collect(FakeProc(), _finished_reader(), box, 5, ev)
    assert res.status == "cancelled"


def test_cancel_during_wait_discards_success():
    from forge_core.agents.sandbox import DockerSandbox

    ev = threading.Event()

    class CancellingProc(FakeProc):
        def wait(self, timeout=None):
            ev.set()
            return 0

    box = {"out": b'{"status":"success","summary":"ok"}\n'}
    res = DockerSandbox._collect(CancellingProc(), _finished_reader(), box, 5, ev)
    assert res.status == "cancelled"


def test_cancel_during_wait_with_unconfirmed_cleanup_reports_cleanup(fake_docker, monkeypatch):
    import subprocess

    from forge_core.agents.sandbox import DockerSandbox

    ev = threading.Event()

    class CancellingProc(FakeProc):
        def wait(self, timeout=None):
            ev.set()
            return 0

    import forge_core.agents.sandbox as sb

    monkeypatch.setattr(sb.subprocess, "Popen", lambda *a, **k: CancellingProc(out=b'{"status":"success"}\n'))
    fake_docker["state"]["ps"] = ("raise", 0, "")
    res = DockerSandbox("img").run(Agent(), {}, 5, ev)
    assert res.error == "cleanup_unconfirmed"


def test_cancel_before_start_is_cancelled_and_destroyed(fake_docker):
    from forge_core.agents.sandbox import DockerSandbox

    ev = threading.Event()
    ev.set()
    res = DockerSandbox("img").run(Agent(), {}, 5, ev)
    assert res.status == "cancelled"
    assert any(c[0] == "rm" for c in fake_docker["calls"])
