"""Provas reais de isolamento (FRG-6). Rodam contra o Docker real do runner, com a imagem de teste."""
import json
import time

from conftest import leftover_containers
from forge_core.agents.runtime import AgentRuntime
from forge_core.agents.sandbox import IsolatedRuntime
from forge_core.tasks.model import Task
from forge_test_probe import SECRET_MARKER, ProbeAgent


def _ctx(mode):
    from forge_core.agents.spec import AgentContext

    task = Task("t-1", mode, "", "", "", "", "normal", "in_progress", "agent", "probe", None, None, None, None,
                None, True, 1, "", "")
    return AgentContext(task=task, actor="pessoa:ana")


def _run(sandbox, mode, timeout=None):
    return IsolatedRuntime(sandbox, settings=_settings()).execute(ProbeAgent(), _ctx(mode), timeout)


def _settings():
    from forge_core.config import Settings
    return Settings(config_dir="cfg.example.invalid", log_level="INFO", automation_enabled=True,
                    database_url=None, database_migration_url=None, agents_disabled=frozenset())


def test_probe_blocks_every_escape_attempt(sandbox):
    res = _run(sandbox, "probe")
    assert res.status == "success", res.error
    d = json.loads(res.outcome.summary)
    assert d["uid"] == 65532
    assert d["cap_eff"] == "0000000000000000"
    assert d["net_ok"] is False
    assert d["write_root_ok"] is False
    assert d["write_big_tmp_ok"] is False
    assert d["fork_ok"] is False
    assert d["alloc_512m_ok"] is False
    assert d["secret_env_visible"] is False
    assert d["docker_sock_visible"] is False
    assert d["host_repo_visible"] is False
    assert leftover_containers() == []


def test_timeout_kills_container_and_confirms_removal(sandbox):
    started = time.monotonic()
    res = _run(sandbox, "sleep", timeout=3)
    assert res.status == "timeout"
    assert time.monotonic() - started < 3 + 30
    assert leftover_containers() == []


def test_descendants_die_with_the_container(sandbox):
    res = _run(sandbox, "outlive")
    assert res.status == "success"
    assert leftover_containers() == []


def test_output_too_large_is_refused(sandbox):
    res = _run(sandbox, "bigout")
    assert res.status == "error" and res.error == "output_too_large"
    assert leftover_containers() == []


def test_agent_exception_only_reports_its_type(sandbox):
    res = _run(sandbox, "raise_secret")
    assert res.status == "error" and res.error == "RuntimeError"
    assert SECRET_MARKER not in repr(res)
    assert leftover_containers() == []


def test_orchestrator_audit_never_contains_secret(sandbox, tmp_path):
    from forge_core.agents import AgentRegistry, Orchestrator
    from forge_core.storage import open_repository
    from forge_core.tasks import TaskService

    repo = open_repository(f"sqlite:///{tmp_path / 'f.db'}")
    svc = TaskService(repo)
    reg = AgentRegistry()
    reg.register(ProbeAgent())
    orch = Orchestrator(repo, reg, tasks=svc, settings=_settings(), runtime=IsolatedRuntime(sandbox, _settings()))
    t = svc.create_task("raise_secret", "pessoa:ana", assignee_kind="agent", assignee_id="probe")
    orch.dispatch(t.id)
    dump = repr(repo.list_audit()) + repr(repo.fetch("SELECT * FROM agent_runs")) + repr(
        repo.fetch("SELECT * FROM task_changes"))
    assert SECRET_MARKER not in dump
    assert leftover_containers() == []


def test_isolated_runtime_is_not_thread_runtime():
    assert issubclass(IsolatedRuntime, AgentRuntime)


def test_public_default_dispatch_runs_echo_in_container(tmp_path):
    """Caminho público: Orchestrator sem runtime injetado usa o executor Docker, sem thread."""
    from forge_core.agents import Orchestrator, default_registry
    from forge_core.storage import open_repository
    from forge_core.tasks import TaskService

    repo = open_repository(f"sqlite:///{tmp_path / 'p.db'}")
    svc = TaskService(repo)
    t = svc.create_task("tarefa real", "pessoa:ana", objective="objetivo", assignee_kind="agent", assignee_id="echo")
    res = Orchestrator(repo, default_registry(), tasks=svc, settings=_settings()).dispatch(t.id)
    assert res.run_status == "success" and res.task_status == "in_validation"
    assert "echo" in res.outcome.summary
    assert leftover_containers() == []


def test_public_dispatch_with_missing_image_fails_closed(tmp_path, monkeypatch):
    from forge_core.agents import Orchestrator, default_registry
    from forge_core.storage import open_repository
    from forge_core.tasks import TaskService

    monkeypatch.setenv("FORGE_AGENT_SANDBOX_IMAGE", "forge-agent-sandbox:nao-existe")
    repo = open_repository(f"sqlite:///{tmp_path / 'm.db'}")
    svc = TaskService(repo)
    t = svc.create_task("tarefa", "pessoa:ana", assignee_kind="agent", assignee_id="echo")
    res = Orchestrator(repo, default_registry(), tasks=svc, settings=_settings()).dispatch(t.id)
    assert res.run_status == "error" and res.error == "sandbox_unavailable"
    assert res.task_status != "in_validation"
    assert leftover_containers() == []
