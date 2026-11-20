"""Setor do agente e passos de execução (migração 0023), mais falha e trava da investigação."""
from __future__ import annotations

import threading

import pytest
from auth_helpers import actor
from test_investigations import REPO, FakeAdapter, _svc

from forge_core.agent_catalog.service import AgentCatalogService, AgentRuleError
from forge_core.agent_catalog.steps import MAX_MESSAGE, ExecutionSteps
from forge_core.agents.provider import ProviderResponse
from forge_core.auth.store import AuthStore
from forge_core.errors import DraftError
from forge_core.investigations.service import AGENT_NAME, InvestigationRuleError
from forge_core.storage.migrate import pending_migrations


def _catalog(repo):
    return AgentCatalogService(repo, AuthStore(repo))


def test_0023_listed_and_columns_exist(make_repo):
    for dialect in ("sqlite", "postgres"):
        assert any(p.stem.startswith("0023_agent_sector_steps") for p in pending_migrations(dialect))
    repo = make_repo()
    repo.fetch("SELECT sector FROM agents LIMIT 0")
    repo.fetch(
        "SELECT execution_id, seq, at, kind, message, input_tokens, output_tokens, duration_ms "
        "FROM agent_execution_events LIMIT 0"
    )


def test_sector_defaults_to_desenvolvimento_and_validates(make_repo):
    repo = make_repo()
    svc = _catalog(repo)
    dona = actor(repo, "dona")
    dev = svc.create(dona, {"name": "a", "scope": "development"})
    assert dev.sector == "desenvolvimento"
    jur = svc.create(dona, {"name": "b", "scope": "development", "sector": "juridico"})
    assert jur.as_json()["sector"] == "juridico"
    with pytest.raises(AgentRuleError) as excinfo:
        svc.create(dona, {"name": "c", "scope": "development", "sector": "rh"})
    assert excinfo.value.code == "invalid_sector"
    sectors = {a["name"]: a["sector"] for a in svc.list_agents(dona)["agents"]}
    assert sectors == {"a": "desenvolvimento", "b": "juridico"}


def test_steps_are_saved_in_order_redacted_and_capped(make_repo):
    repo = make_repo()
    svc = _catalog(repo)
    dona = actor(repo, "dona")
    agent = svc.create(dona, {"name": "a", "scope": "development"})
    steps = ExecutionSteps()
    steps.step("Contexto montado")
    steps.model("Resposta", usage={"input_tokens": 7, "output_tokens": 3}, duration_ms=1200)
    steps.error("falhou com token=ghp_" + "A" * 36)
    steps.step("x" * (MAX_MESSAGE + 50))
    svc.record_execution(agent.id, status="error", event="run", steps=steps)
    detail = svc.get_agent(dona, agent.id)
    got = detail["executions"][0]["steps"]
    assert [s["kind"] for s in got] == ["step", "model", "error", "step"]
    assert [s["seq"] for s in got] == [1, 2, 3, 4]
    assert got[1]["input_tokens"] == 7 and got[1]["output_tokens"] == 3 and got[1]["duration_ms"] == 1200
    assert "ghp_" not in got[2]["message"]
    assert len(got[3]["message"]) == MAX_MESSAGE


def test_execution_without_steps_has_empty_list(make_repo):
    repo = make_repo()
    svc = _catalog(repo)
    dona = actor(repo, "dona")
    agent = svc.create(dona, {"name": "a", "scope": "development"})
    svc.record_execution(agent.id, status="ok")
    assert svc.get_agent(dona, agent.id)["executions"][0]["steps"] == []


def _investigation_executions(repo):
    return repo.fetch(
        "SELECT e.id, e.status, e.event FROM agent_executions e JOIN agents a ON a.id = e.agent_id "
        "WHERE a.name = ? ORDER BY e.started_at", (AGENT_NAME,),
    )


def _steps_of(repo, execution_id):
    return repo.fetch(
        "SELECT kind, message FROM agent_execution_events WHERE execution_id = ? ORDER BY seq", (execution_id,),
    )


def test_investigation_success_records_steps(make_repo):
    repo = make_repo()
    adapter = FakeAdapter()
    adapter.complete = lambda prompt, max_tokens=None: ProviderResponse(
        text="ok", usage={"input_tokens": 10, "output_tokens": 20, "model": "claude-sonnet-5-5"},
    )
    svc = _svc(repo, provider=adapter)
    svc.run(actor(repo, "ana"), {"description": "Investigar lentidão", "repos": [REPO]})
    (exec_id, status, _event), = _investigation_executions(repo)
    assert status == "ok"
    kinds = [k for k, _ in _steps_of(repo, exec_id)]
    assert kinds == ["step", "step", "model", "step"]
    assert "claude-sonnet-5-5" in _steps_of(repo, exec_id)[2][1]


@pytest.mark.parametrize("failure, code", [(DraftError("claude_cli_error"), "claude_cli_error"),
                                           (RuntimeError("boom"), "provider_error")])
def test_investigation_failure_is_recorded_as_error(make_repo, failure, code):
    repo = make_repo()
    adapter = FakeAdapter()

    def boom(prompt, max_tokens=None):
        raise failure

    adapter.complete = boom
    svc = _svc(repo, provider=adapter)
    with pytest.raises((DraftError, InvestigationRuleError)):
        svc.run(actor(repo, "ana"), {"description": "Investigar lentidão", "repos": [REPO]})
    (exec_id, status, event), = _investigation_executions(repo)
    assert status == "error"
    assert code in event
    assert _steps_of(repo, exec_id)[-1][0] == "error"
    assert repo.fetch("SELECT count(*) FROM investigation_notes")[0][0] == 0


def test_investigation_refuses_second_run_while_one_is_running(make_repo):
    repo = make_repo()
    entered = threading.Event()
    release = threading.Event()
    adapter = FakeAdapter()

    def slow(prompt, max_tokens=None):
        entered.set()
        release.wait(5)
        return ProviderResponse(text="ok")

    adapter.complete = slow
    svc = _svc(repo, provider=adapter)
    ana = actor(repo, "ana")
    payload = {"description": "Investigar lentidão", "repos": [REPO]}
    worker = threading.Thread(target=lambda: svc.run(ana, payload))
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(InvestigationRuleError) as excinfo:
            svc.run(ana, payload)
        assert excinfo.value.code == "busy"
    finally:
        release.set()
        worker.join(5)
    svc.run(ana, payload)  # liberou depois de terminar
