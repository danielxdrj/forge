"""Radar de prioridades: pontuação determinística, rodada, histórico, agenda e rotas."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from auth_helpers import TEST_CLIENT_ID, FakeGitHub, actor, bootstrap, person

from forge_core.agents.provider import ProviderResponse
from forge_core.ai_settings import AiSettings
from forge_core.auth.store import AuthStore
from forge_core.config import load_settings
from forge_core.draft.github_gh import _open_item
from forge_core.errors import AuthorizationError, ConfigError, DraftError
from forge_core.radar.scoring import NOW_LIMIT, analyze, score_item
from forge_core.radar.service import (
    AGENT_NAME,
    RadarError,
    RadarScheduler,
    RadarService,
    next_run,
)
from forge_core.storage.migrate import pending_migrations
from forge_core.storage.seed import seed_allowed_repos

NOW = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)  # 11:00 em São Paulo
ALLOWED = {"ferreiraeborzone/site"}


def _item(number=1, **kw):
    base = {
        "repo": "ferreiraeborzone/site",
        "number": number,
        "title": f"Issue {number}",
        "url": f"https://github.com/ferreiraeborzone/site/issues/{number}",
        "created_at": "2026-11-10T10:00:00Z",
        "issue_updated_at": "2026-11-15T10:00:00Z",
        "item_updated_at": "2026-11-15T10:00:00Z",
        "status": "Backlog",
        "status_changed_at": "2026-11-15T10:00:00Z",
        "tipo": "Manutenção",
        "prioridade": "Média",
        "size": "3",
        "escopo": "",
        "sprint": {},
        "start_date": "",
        "target_date": "",
        "labels": [],
        "assignees": ["ana"],
    }
    base.update(kw)
    return base


def _score(item, stale_days=14):
    return score_item(item, now=NOW, stale_days=stale_days, allowed_repos=ALLOWED)


# --- pontuação -------------------------------------------------------------------------------

def test_priority_drives_base_score():
    assert _score(_item(prioridade="Urgente"))["score"] == 40
    assert _score(_item(prioridade="Alta"))["score"] == 25
    assert _score(_item(prioridade="Média"))["score"] == 10
    assert _score(_item(prioridade="Baixa"))["score"] == 0
    assert _score(_item(prioridade=""))["score"] == 5
    assert _score(_item(prioridade="Urgente"))["reasons"] == ["Prioridade Urgente"]


def test_done_items_are_ignored():
    assert _score(_item(status="Concluído")) is None


def test_stale_counts_last_activity_of_issue_and_board_item():
    item = _item(issue_updated_at="2026-10-01T10:00:00Z", item_updated_at="2026-10-20T10:00:00Z")
    scored = _score(item)
    assert scored["idle_days"] == 27
    assert "Parada há 27 dias" in scored["reasons"]
    assert scored["score"] == 10 + 10 + 13
    assert _score(_item(issue_updated_at="2026-11-10T10:00:00Z"))["idle_days"] == 1


def test_security_sprint_target_and_unassigned_signals():
    item = _item(
        prioridade="Alta", tipo="Security Project", assignees=[],
        sprint={"title": "Sprint 14", "start": "2026-11-01", "duration": 7},
        target_date="2026-11-12",
    )
    scored = _score(item)
    assert scored["score"] == 25 + 20 + 15 + 20 + 5
    assert scored["reasons"] == [
        "Prioridade Alta", "Segurança", "Sprint 14 encerrada em 07/11", "Prazo vencido em 12/11", "Sem responsável",
    ]


def test_reopened_and_waiting_validation():
    assert "Reaberta" in _score(_item(status="Reaberto"))["reasons"]
    waiting = _score(_item(status="Aguardando validação", status_changed_at="2026-11-01T10:00:00Z"))
    assert "Aguardando validação há 15 dias" in waiting["reasons"]


def test_investigable_only_inside_allowlist():
    assert _score(_item())["investigable"] is True
    assert _score(_item(repo="ferreiraeborzone/outro"))["investigable"] is False


def test_analyze_sections_are_deterministic_and_bounded():
    items = [_item(n, prioridade="Urgente") for n in range(1, 9)]
    items.append(_item(20, prioridade="", size="", status="Triagem", status_changed_at="2026-11-01T10:00:00Z"))
    items.append(_item(30, issue_updated_at="2026-09-01T10:00:00Z", item_updated_at="2026-09-01T10:00:00Z"))
    first = analyze(items, now=NOW, stale_days=14, allowed_repos=ALLOWED)
    second = analyze(list(reversed(items)), now=NOW, stale_days=14, allowed_repos=ALLOWED)
    assert [e["key"] for e in first["now"]] == [e["key"] for e in second["now"]]
    assert len(first["now"]) == NOW_LIMIT
    assert [e["number"] for e in first["stale"]] == [30]
    triage = next(e for e in first["investigate"] if e["number"] == 20)
    assert "Na triagem há 15 dias" in triage["investigate_reasons"]
    assert "Sem prioridade definida" in triage["investigate_reasons"]
    assert first["stats"] == {"open": 10, "now": 5, "stale": 1, "urgent": 8, "unassigned": 0}


def test_open_item_parser_reads_board_fields():
    node = {
        "updatedAt": "2026-11-10T14:22:01Z",
        "fieldValues": {"nodes": [
            {},
            {"name": "Em atendimento", "updatedAt": "2026-11-10T02:18:20Z", "field": {"name": "Status"}},
            {"name": "Alta", "field": {"name": "Prioridade"}},
            {"name": "5", "field": {"name": "Size"}},
            {"name": "Relatório", "field": {"name": "Escopo"}},
            {"title": "Sprint 15", "startDate": "2026-11-07", "duration": 7, "field": {"name": "Sprint"}},
            {"date": "2026-11-20", "field": {"name": "Target date"}},
        ]},
        "content": {
            "number": 1488, "title": "fix: x", "url": "https://github.com/o/r/issues/1488", "state": "OPEN",
            "createdAt": "2026-11-09T21:49:44Z", "updatedAt": "2026-11-09T21:49:44Z",
            "repository": {"nameWithOwner": "o/r"}, "labels": {"nodes": [{"name": "bug"}]},
            "assignees": {"nodes": [{"login": "danielxdrj"}]},
        },
    }
    item = _open_item(node)
    assert item["status"] == "Em atendimento"
    assert item["prioridade"] == "Alta"
    assert item["size"] == "5"
    assert item["escopo"] == "Relatório"
    assert item["sprint"] == {"title": "Sprint 15", "start": "2026-11-07", "duration": 7}
    assert item["target_date"] == "2026-11-20"
    assert item["assignees"] == ["danielxdrj"]
    assert _open_item({**node, "content": {**node["content"], "state": "CLOSED"}}) is None
    assert _open_item({**node, "content": {}}) is None


# --- serviço ---------------------------------------------------------------------------------

class FakeBoardGh:
    def __init__(self, items=None, error=None):
        self.items = items if items is not None else [
            _item(1, prioridade="Urgente", title="Corrigir boleto token=ghp_" + "C" * 36),
            _item(2, issue_updated_at="2026-09-01T10:00:00Z", item_updated_at="2026-09-01T10:00:00Z"),
        ]
        self.error = error
        self.calls = 0

    def list_open_project_items(self, limit=300):
        self.calls += 1
        if self.error:
            raise DraftError(self.error)
        return self.items


class FakeSummary:
    name = "fake-radar"

    def __init__(self, text="- Concluir ferreiraeborzone/site#1 primeiro.", error=None):
        self.text = text
        self.error = error
        self.prompts = []

    def complete(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        if self.error:
            raise DraftError(self.error)
        return ProviderResponse(
            text=self.text,
            usage={"input_tokens": 5, "output_tokens": 300, "cache_read_tokens": 9000, "cache_write_tokens": 2000,
                   "turns": 1, "model": "claude-opus-5-5"},
            cost=0.12,
        )


def _settings(tmp_path, **env):
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = {"FORGE_CONFIG_DIR": str(tmp_path), "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID}
    base.update(env)
    return load_settings(base)


def _svc(repo, tmp_path, gh=None, provider=None):
    seed_allowed_repos(repo)
    store = AuthStore(repo)
    return RadarService(
        repo, store, _settings(tmp_path), gh=gh or FakeBoardGh(),
        provider=provider or FakeSummary(), clock=lambda: NOW, ai_settings=AiSettings(repo, store, env={}),
    )


def test_0020_listed_for_both_dialects(make_repo):
    assert any(p.stem.startswith("0020_radar_reports") for p in pending_migrations("sqlite"))
    assert any(p.stem.startswith("0020_radar_reports") for p in pending_migrations("postgres"))
    repo = make_repo()
    repo.fetch("SELECT id, created_at, reason, status, error_code, summary, payload, created_by FROM radar_reports LIMIT 0")


def test_run_saves_report_summary_and_agent_execution(make_repo, tmp_path):
    repo = make_repo()
    provider = FakeSummary()
    svc = _svc(repo, tmp_path, provider=provider)
    report = svc.run_now("manual", "tester")
    assert report["status"] == "ok"
    assert report["summary"].startswith("- Concluir")
    assert [e["number"] for e in report["now"]] == [1]
    assert [e["number"] for e in report["stale"]] == [2]
    assert "ghp_" not in provider.prompts[0]
    agents = repo.fetch("SELECT id, name, scope FROM agents WHERE name = ?", (AGENT_NAME,))
    assert len(agents) == 1
    execs = repo.fetch(
        "SELECT status, event, output_tokens, cache_read_tokens, model, cost_usd FROM agent_executions WHERE agent_id = ?",
        (agents[0][0],),
    )
    assert execs == [("ok", "1 para concluir já, 1 paradas, 2 abertas", 300, 9000, "claude-opus-5-5", 0.12)]
    assert report["usage"]["cost_usd"] == 0.12
    assert report["reused_summary"] is False
    svc.run_now("schedule", "sistema:radar")
    assert len(repo.fetch("SELECT id FROM agents WHERE name = ?", (AGENT_NAME,))) == 1


def test_agent_trigger_follows_settings(make_repo, tmp_path):
    repo = make_repo()
    svc = _svc(repo, tmp_path)
    svc.run_now("manual", "tester")
    trigger = repo.fetch("SELECT trigger, engine FROM agents WHERE name = ?", (AGENT_NAME,))[0]
    assert trigger == ("manual (agenda automática desligada)", "Claude Code CLI · modelo padrão")
    AiSettings(repo, AuthStore(repo), env={}).update(
        actor(repo, "dona"), {"radar": {"auto": True, "time": "13:00", "model": "claude-haiku-5-5"}},
    )
    svc.sync_agent()
    trigger = repo.fetch("SELECT trigger, engine FROM agents WHERE name = ?", (AGENT_NAME,))[0]
    assert trigger == ("automático, todo dia às 13:00 (e manual)", "Claude Code CLI · Claude Haiku 5.5")


def test_unchanged_backlog_reuses_summary_without_calling_engine(make_repo, tmp_path):
    repo = make_repo()
    provider = FakeSummary()
    gh = FakeBoardGh()
    svc = _svc(repo, tmp_path, gh=gh, provider=provider)
    first = svc.run_now("manual", "tester")
    second = svc.run_now("schedule", "sistema:radar")
    assert len(provider.prompts) == 1
    assert second["summary"] == first["summary"]
    assert second["reused_summary"] is True
    assert second["usage"] == {}
    reused = [row for row in repo.fetch("SELECT event, cost_usd FROM agent_executions")
              if row[0].endswith("sem mudanças, resumo reaproveitado")]
    assert reused == [(reused[0][0], None)]
    gh.items = gh.items + [_item(3, prioridade="Urgente", title="Nova urgência")]
    third = svc.run_now("schedule", "sistema:radar")
    assert third["reused_summary"] is False
    assert len(provider.prompts) == 2


def test_summary_failure_keeps_report(make_repo, tmp_path):
    repo = make_repo()
    svc = _svc(repo, tmp_path, provider=FakeSummary(error="claude_cli_error"))
    report = svc.run_now("manual", "tester")
    assert report["status"] == "ok"
    assert report["summary"] == ""
    assert report["summary_error"] == "claude_cli_error"
    assert report["now"]


def test_board_failure_records_error_report(make_repo, tmp_path):
    repo = make_repo()
    svc = _svc(repo, tmp_path, gh=FakeBoardGh(error="project_scope"))
    report = svc.run_now("schedule", "sistema:radar")
    assert report["status"] == "error"
    assert report["error"] == "project_scope"
    execs = repo.fetch("SELECT status, event, cost_usd FROM agent_executions")
    assert execs == [("error", "falha: project_scope", None)]


def test_overview_history_and_roles(make_repo, tmp_path):
    repo = make_repo()
    svc = _svc(repo, tmp_path)
    ana = actor(repo, "ana")
    empty = svc.overview(ana)
    assert empty["latest"] is None
    assert empty["auto"] is False
    assert empty["time"] == "13:00"
    assert empty["schedule"] == []
    assert empty["next_run"] is None
    AiSettings(repo, AuthStore(repo), env={}).update(actor(repo, "dona"), {"radar": {"auto": True}})
    on = svc.overview(ana)
    assert on["schedule"] == ["13:00"]
    assert on["next_run"].startswith("2026-11-16T13:00")
    first = svc.run_now("manual", ana.identity_id)
    assert svc.overview(ana)["latest"]["id"] == first["id"]
    history = svc.history(ana)
    assert history[0]["id"] == first["id"]
    assert svc.get(ana, first["id"])["now"]
    with pytest.raises(RadarError):
        svc.get(ana, "nao-existe")
    with pytest.raises(AuthorizationError):
        svc.overview(actor(repo, "solta"))


def test_busy_rejects_parallel_run(make_repo, tmp_path):
    repo = make_repo()
    svc = _svc(repo, tmp_path)
    assert svc._lock.acquire(blocking=False)
    try:
        with pytest.raises(RadarError) as excinfo:
            svc.run_now("manual", "x")
        assert excinfo.value.code == "busy"
        assert svc.run_scheduled() is None
    finally:
        svc._lock.release()


# --- agenda ----------------------------------------------------------------------------------

def test_next_run_uses_local_timezone():
    times = ("11:00", "15:40", "17:50")
    assert next_run(datetime(2026, 11, 16, 13, 0, tzinfo=UTC), times, "America/Sao_Paulo").startswith("2026-11-16T11:00")
    assert next_run(datetime(2026, 11, 16, 21, 0, tzinfo=UTC), times, "America/Sao_Paulo").startswith("2026-11-17T11:00")
    assert next_run(NOW, (), "America/Sao_Paulo") is None


def test_scheduler_fires_once_a_day_and_respects_toggle(make_repo, tmp_path):
    repo = make_repo()
    gh = FakeBoardGh()
    svc = _svc(repo, tmp_path, gh=gh)
    dona = actor(repo, "dona")
    ai = AiSettings(repo, AuthStore(repo), env={})
    clock = {"now": datetime(2026, 11, 16, 16, 0, 30, tzinfo=UTC)}
    sched = RadarScheduler(svc, _settings(tmp_path), clock=lambda: clock["now"])
    assert sched.tick() is False  # desligado por padrão: não roda nem no horário
    ai.update(dona, {"radar": {"auto": True, "time": "11:00"}})
    clock["now"] = datetime(2026, 11, 16, 13, 59, tzinfo=UTC)
    assert sched.tick() is False
    clock["now"] = datetime(2026, 11, 16, 14, 0, 30, tzinfo=UTC)
    assert sched.tick() is True
    assert sched.tick() is False
    clock["now"] = datetime(2026, 11, 16, 18, 45, tzinfo=UTC)
    assert sched.tick() is False
    ai.update(dona, {"radar": {"auto": False}})
    clock["now"] = datetime(2026, 11, 17, 14, 1, tzinfo=UTC)
    assert sched.tick() is False
    ai.update(dona, {"radar": {"auto": True, "time": "16:30"}})
    clock["now"] = datetime(2026, 11, 17, 19, 31, tzinfo=UTC)
    assert sched.tick() is True
    assert gh.calls == 2


def test_radar_settings_validation(tmp_path):
    settings = _settings(tmp_path)
    assert settings.radar_stale_days == 14
    assert settings.radar_timezone == "America/Sao_Paulo"
    for env in ({"FORGE_RADAR_STALE_DAYS": "0"}, {"FORGE_RADAR_TIMEZONE": "Lua/Base"}):
        with pytest.raises(ConfigError):
            _settings(tmp_path, **env)


# --- rotas -----------------------------------------------------------------------------------

def test_radar_routes(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    assert fastapi
    from fastapi.testclient import TestClient
    from test_web_investigations import HOST, Scripted, _h, _login

    from forge_core.storage import open_repository
    from forge_core.web.app import create_app

    settings = _settings(tmp_path, FORGE_DATABASE_URL=f"sqlite:///{tmp_path / 'r.db'}",
                         FORGE_WEB_HOSTS="127.0.0.1:8090,localhost:8090")
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub())
    person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    app = create_app(repo, settings, transport=Scripted(), gh=FakeBoardGh(), radar_provider=FakeSummary(),
                     drafts_dir=tmp_path / "drafts")
    client = TestClient(app, base_url="http://127.0.0.1:8090")
    assert client.get("/api/radar", headers=HOST).status_code == 401
    csrf = _login(client)
    overview = client.get("/api/radar", headers=HOST)
    assert overview.status_code == 200
    assert overview.json()["schedule"] == []
    report = app.state.radar.run_now("manual", "tester")
    listed = client.get("/api/radar/reports", headers=HOST).json()["reports"]
    assert listed[0]["id"] == report["id"]
    got = client.get(f"/api/radar/reports/{report['id']}", headers=HOST)
    assert got.status_code == 200
    assert client.get("/api/radar/reports/xyz", headers=HOST).status_code == 404
    started = client.post("/api/radar/run", headers=_h(csrf))
    assert started.status_code in (202, 409)


def test_agent_detail_exposes_and_protects_radar_config(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_web_investigations import HOST, Scripted, _h, _login

    from forge_core.storage import open_repository
    from forge_core.web.app import create_app

    settings = _settings(tmp_path, FORGE_DATABASE_URL=f"sqlite:///{tmp_path / 'c.db'}",
                         FORGE_WEB_HOSTS="127.0.0.1:8090,localhost:8090")
    repo = open_repository(settings.database_url)
    seed_allowed_repos(repo)
    owner = bootstrap(repo, FakeGitHub())
    person(repo, owner, FakeGitHub(), "maria", 42, "editor")
    app = create_app(repo, settings, transport=Scripted(), gh=FakeBoardGh(), radar_provider=FakeSummary(),
                     drafts_dir=tmp_path / "drafts")
    agent_id = app.state.radar.ensure_agent()
    client = TestClient(app, base_url="http://127.0.0.1:8090")
    csrf = _login(client)
    detail = client.get(f"/api/agents/{agent_id}", headers=HOST).json()
    assert detail["config"]["kind"] == "radar"
    assert detail["config"]["auto"] is False
    assert detail["config"]["time"] == "13:00"
    assert detail["config"]["can_edit"] is False
    assert detail["agent"]["trigger"] == "manual (agenda automática desligada)"
    denied = client.post(f"/api/agents/{agent_id}/config", headers=_h(csrf), json={"auto": True})
    assert denied.status_code == 403
    assert app.state.radar.schedule() == (False, "13:00")
