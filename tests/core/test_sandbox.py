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

    def run(self, agent, payload, timeout):
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
    b'{"status":"error","error":"' + b"e" * 81 + b'"}\n',
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
    res = DockerSandbox("img").run("echo", {}, 5)
    assert res.status == "error" and res.error == "docker_unavailable"
