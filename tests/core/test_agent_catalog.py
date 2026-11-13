"""Catálogo/governança de agentes: migração 0019, CRUD, métricas e aprovação de escrita."""
from __future__ import annotations

import pytest
from auth_helpers import actor

from forge_core.agent_catalog.seed import DEMO_AGENTS, seed_demo_agents
from forge_core.agent_catalog.service import AgentCatalogService, AgentRuleError
from forge_core.auth.store import AuthStore
from forge_core.errors import AuthorizationError
from forge_core.storage.migrate import pending_migrations


def _svc(repo):
    return AgentCatalogService(repo, AuthStore(repo))


def test_0019_listed_for_both_dialects_and_tables_exist(make_repo):
    sqlite = [p.stem for p in pending_migrations("sqlite")]
    postgres = [p.stem for p in pending_migrations("postgres")]
    assert any(s.startswith("0019_agents_governance") for s in sqlite)
    assert any(s.startswith("0019_agents_governance") for s in postgres)
    repo = make_repo()
    repo.fetch(
        "SELECT id, name, scope, status, trigger, engine, permissions_read, "
        "permissions_write, permissions_denied FROM agents LIMIT 0"
    )
    repo.fetch("SELECT id, agent_id, started_at, status, event, duration_ms, log FROM agent_executions LIMIT 0")
    repo.fetch("SELECT id, agent_id, action, status, requested_at, decided_by FROM agent_approvals LIMIT 0")


def test_create_requires_owner(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    ana = actor(repo, "ana")
    with pytest.raises(AuthorizationError):
        svc.create(ana, {"name": "x", "scope": "development"})


def test_create_validates_scope_and_status(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    with pytest.raises(AgentRuleError) as excinfo:
        svc.create(dona, {"name": "x", "scope": "invalido"})
    assert excinfo.value.code == "invalid_scope"
    with pytest.raises(AgentRuleError) as excinfo:
        svc.create(dona, {"name": "x", "scope": "development", "status": "invalido"})
    assert excinfo.value.code == "invalid_status"


@pytest.mark.parametrize("resource", ["ftp", "database", "db", "portainer", "docker", "mysql", "postgres"])
def test_create_always_denies_write_to_locked_resources(make_repo, resource):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    with pytest.raises(AgentRuleError) as excinfo:
        svc.create(dona, {
            "name": f"agente-{resource}", "scope": "development",
            "permissions_write": [resource],
        })
    assert excinfo.value.code == "write_denied_resource"


def test_create_development_scope_with_allowed_write_needs_no_approval(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    view = svc.create(dona, {
        "name": "writer-dev", "scope": "development", "permissions_write": ["github"],
    })
    approvals = svc.list_approvals(dona)
    assert [a for a in approvals if a.agent_id == view.id] == []


def test_create_company_system_scope_with_write_creates_pending_approval(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    view = svc.create(dona, {
        "name": "writer-prod", "scope": "company_system", "permissions_write": ["github"],
    })
    approvals = [a for a in svc.list_approvals(dona) if a.agent_id == view.id]
    assert len(approvals) == 1
    assert approvals[0].status == "pending"
    assert approvals[0].action == "write_access"


def test_create_duplicate_name_rejected(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    svc.create(dona, {"name": "duplicado", "scope": "development"})
    with pytest.raises(AgentRuleError) as excinfo:
        svc.create(dona, {"name": "duplicado", "scope": "development"})
    assert excinfo.value.code == "name_taken"


def test_list_and_get_agent_with_metrics_and_executions(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    ana = actor(repo, "ana")
    a1 = svc.create(dona, {"name": "a1", "scope": "development"})
    svc.create(dona, {"name": "a2", "scope": "development", "status": "paused"})
    svc.record_execution(a1.id, status="ok", event="run 1")
    svc.record_execution(a1.id, status="error", event="run 2", log="falhou")
    listed = svc.list_agents(ana)
    assert listed["metrics"]["total"] == 2
    assert listed["metrics"]["active"] == 1
    assert listed["metrics"]["executions_today"] == 2
    assert listed["metrics"]["errors_24h"] == 1
    detail = svc.get_agent(ana, a1.id)
    assert detail["agent"]["id"] == a1.id
    assert len(detail["executions"]) == 2


def test_update_status_pauses_agent(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    agent = svc.create(dona, {"name": "pausavel", "scope": "development"})
    updated = svc.update(dona, agent.id, {"status": "paused"})
    assert updated.status == "paused"


def test_update_requires_owner(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    ana = actor(repo, "ana")
    agent = svc.create(dona, {"name": "so-owner", "scope": "development"})
    with pytest.raises(AuthorizationError):
        svc.update(ana, agent.id, {"status": "paused"})


def test_decide_approval_approve_and_reject(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    agent = svc.create(dona, {
        "name": "aprovar", "scope": "company_system", "permissions_write": ["github"],
    })
    pending = next(a for a in svc.list_approvals(dona) if a.agent_id == agent.id)
    decided = svc.decide_approval(dona, pending.id, "approved")
    assert decided.status == "approved"
    assert decided.decided_by == dona.identity_id
    with pytest.raises(AgentRuleError) as excinfo:
        svc.decide_approval(dona, pending.id, "rejected")
    assert excinfo.value.code == "already_decided"


def test_decide_approval_requires_owner(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    ana = actor(repo, "ana")
    agent = svc.create(dona, {
        "name": "aprovar2", "scope": "company_system", "permissions_write": ["github"],
    })
    pending = next(a for a in svc.list_approvals(dona) if a.agent_id == agent.id)
    with pytest.raises(AuthorizationError):
        svc.decide_approval(ana, pending.id, "approved")


def test_approving_never_unlocks_ftp_db_portainer_write(make_repo):
    """Mesmo aprovado, o agente nunca tem permissions_write com recurso travado — a validação
    recusa isso na criação; aprovar só decide o pedido existente, não adiciona permissão nova."""
    repo = make_repo()
    svc = _svc(repo)
    dona = actor(repo, "dona")
    agent = svc.create(dona, {
        "name": "sempre-sem-acesso", "scope": "company_system", "permissions_write": ["github"],
    })
    pending = next(a for a in svc.list_approvals(dona) if a.agent_id == agent.id)
    svc.decide_approval(dona, pending.id, "approved")
    reloaded = svc.get_agent(dona, agent.id)["agent"]
    for resource in ("ftp", "database", "portainer", "docker"):
        assert resource not in reloaded["permissions"]["write"]


def test_seed_demo_agents_disabled_by_default_is_noop(make_repo):
    repo = make_repo()
    assert seed_demo_agents(repo, enabled=False) == 0
    assert repo.fetch("SELECT COUNT(*) FROM agents")[0][0] == 0


def test_seed_demo_agents_enabled_only_when_table_empty(make_repo):
    repo = make_repo()
    created = seed_demo_agents(repo, enabled=True)
    assert created == len(DEMO_AGENTS)
    again = seed_demo_agents(repo, enabled=True)
    assert again == 0
    assert repo.fetch("SELECT COUNT(*) FROM agents")[0][0] == len(DEMO_AGENTS)
