"""Investigação livre (sem issue): migração 0018, validação, prompt sem segredo, persistência."""
from __future__ import annotations

import pytest
from auth_helpers import actor

from forge_core.agents.provider import ProviderResponse
from forge_core.auth.store import AuthStore
from forge_core.errors import AuthorizationError, DraftError
from forge_core.investigations.service import (
    InvestigationRuleError,
    InvestigationService,
)
from forge_core.notes.service import NoteService
from forge_core.storage.migrate import pending_migrations
from forge_core.storage.seed import seed_allowed_repos

REPO = "ferreiraeborzone/site"
SECRET_SENTINEL = "SEGREDO_NUNCA_NO_PROMPT_xyz123"


class FakeAdapter:
    name = "fake-investigation"

    def __init__(self, text="achado: nada crítico"):
        self.text = text
        self.prompts = []

    def complete(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        return ProviderResponse(text=self.text)


def _svc(repo, provider=None, **kw):
    seed_allowed_repos(repo)
    return InvestigationService(repo, AuthStore(repo), provider=provider or FakeAdapter(), **kw)


def test_0018_listed_for_both_dialects_and_columns_exist(make_repo):
    sqlite = [p.stem for p in pending_migrations("sqlite")]
    postgres = [p.stem for p in pending_migrations("postgres")]
    assert any(s.startswith("0018_investigations") for s in sqlite)
    assert any(s.startswith("0018_investigations") for s in postgres)
    repo = make_repo()
    repo.fetch(
        "SELECT id, issue_key, title, body, kind, repos_json, connection_ids_json, engine, description "
        "FROM investigation_notes LIMIT 0"
    )


def test_run_persists_investigation_and_redacts_secret(make_repo):
    repo = make_repo()
    adapter = FakeAdapter(text=f"achado com {SECRET_SENTINEL} token=ghp_" + "A" * 36)
    svc = _svc(repo, provider=adapter)
    ana = actor(repo, "ana")
    view = svc.run(ana, {"description": "Investigar lentidão no login", "repos": [REPO]})
    assert view.description == "Investigar lentidão no login"
    assert view.title == "Investigar lentidão no login"
    assert view.repos == (REPO,)
    assert "ghp_" not in view.result
    assert "***" in view.result
    loaded = svc.get_investigation(ana, view.id)
    assert loaded.id == view.id
    listed = svc.list_investigations(ana)
    assert len(listed) == 1
    assert listed[0].id == view.id


def test_run_requires_editor_or_owner(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    solta = actor(repo, "solta")
    with pytest.raises(AuthorizationError):
        svc.run(solta, {"description": "x", "repos": [REPO]})


def test_run_rejects_repo_outside_allowlist(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"description": "x", "repos": ["evil/out"]})
    assert excinfo.value.code == "repo_not_allowed"


def test_run_rejects_empty_description(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"description": "   ", "repos": [REPO]})
    assert excinfo.value.code == "invalid_description"


def test_run_accepts_optional_issue_key(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    ana = actor(repo, "ana")
    view = svc.run(ana, {"description": "x", "repos": [REPO], "issue_key": f"{REPO}#9"})
    assert view.issue_key == f"{REPO}#9"


def test_connection_metadata_in_prompt_never_includes_secret(make_repo):
    repo = make_repo()
    ts = "2026-11-13T00:00:00+00:00"
    repo._run([
        (
            (
                "INSERT INTO connections (id, name, type, username, port, database_name, remote_path, "
                "secret_ciphertext, preferred_host_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            ("c1", "ftp-prod", "ftp", "admin", 21, None, "/www", SECRET_SENTINEL, None, ts, ts),
        )
    ])
    adapter = FakeAdapter()
    svc = _svc(repo, provider=adapter)
    ana = actor(repo, "ana")
    svc.run(ana, {"description": "checar arquivos", "repos": [REPO], "connection_ids": ["c1"]})
    assert len(adapter.prompts) == 1
    prompt = adapter.prompts[0]
    assert "ftp-prod" in prompt
    assert SECRET_SENTINEL not in prompt
    assert "secret_ciphertext" not in prompt


def test_prompt_never_leaks_forge_env_markers(make_repo):
    repo = make_repo()
    adapter = FakeAdapter()
    svc = _svc(repo, provider=adapter)
    ana = actor(repo, "ana")
    svc.run(ana, {"description": "pergunta normal sem segredo", "repos": [REPO]})
    assert "FORGE_" not in adapter.prompts[0]
    assert "GH_TOKEN" not in adapter.prompts[0]


def test_investigation_hidden_from_notes_api_and_notes_hidden_from_investigations(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    store = AuthStore(repo)
    notes = NoteService(repo, store)
    inv = InvestigationService(repo, store, provider=FakeAdapter())
    ana = actor(repo, "ana")
    note = notes.create(ana, {"issue_key": f"{REPO}#9", "title": "nota manual", "body": "x"})
    investigation = inv.run(ana, {"description": "investigar x", "repos": [REPO]})
    assert note.id not in [i.id for i in inv.list_investigations(ana)]
    assert investigation.id not in [n.id for n in notes.list_notes(ana)]


def test_note_without_issue_key_allowed(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    notes = NoteService(repo, AuthStore(repo))
    ana = actor(repo, "ana")
    note = notes.create(ana, {"title": "nota solta", "body": "sem issue"})
    assert note.issue_key is None
    assert notes.get_note(ana, note.id).id == note.id


# --- Pedido automático (modo "issue") ---------------------------------------------------------

class FakeIssueGh:
    """gh falso: só a leitura da issue usada como pedido."""

    def __init__(self, detail=None, error=None):
        self.detail = detail or {
            "number": 42,
            "url": f"https://github.com/{REPO}/issues/42",
            "title": "Formulário de contato não valida telefone",
            "body": "Telefone sem DDD passa. Ver FORGE_ENGINE no ambiente. token=ghp_" + "B" * 36,
            "state": "OPEN",
            "labels": [{"name": "bug"}, {"name": "site"}],
            "comments": [
                {"author": {"login": "maria"}, "body": "Acontece também no celular."},
                {"author": {"login": "joao"}, "body": ""},
            ],
        }
        self.error = error
        self.calls = []

    def view_issue_request(self, number, repo):
        self.calls.append((number, repo))
        if self.error:
            raise DraftError(self.error)
        return self.detail


def _issue_svc(repo, gh=None, provider=None):
    seed_allowed_repos(repo)
    return InvestigationService(repo, AuthStore(repo), provider=provider or FakeAdapter(), gh=gh or FakeIssueGh())


def test_issue_mode_uses_issue_as_request_without_description(make_repo):
    repo = make_repo()
    adapter = FakeAdapter()
    gh = FakeIssueGh()
    svc = _issue_svc(repo, gh=gh, provider=adapter)
    ana = actor(repo, "ana")
    view = svc.run(ana, {"mode": "issue", "issue_key": f"{REPO}#42"})
    assert gh.calls == [(42, REPO)]
    prompt = adapter.prompts[0]
    assert "Formulário de contato não valida telefone" in prompt
    assert "Telefone sem DDD passa." in prompt
    assert "labels: bug, site" in prompt
    assert "@maria: Acontece também no celular." in prompt
    assert "Investigue a issue abaixo" in prompt
    assert "ghp_" not in prompt
    assert view.repos == (REPO,)
    assert view.issue_key == f"{REPO}#42"
    assert view.title.startswith(f"{REPO}#42 — ")
    assert "Pedido automático" in view.description


def test_issue_mode_appends_complement(make_repo):
    repo = make_repo()
    adapter = FakeAdapter()
    svc = _issue_svc(repo, provider=adapter)
    ana = actor(repo, "ana")
    view = svc.run(ana, {"mode": "issue", "issue_key": f"{REPO}#42", "description": "Foque no front-end."})
    assert "## Complemento de quem pediu\nFoque no front-end." in adapter.prompts[0]
    assert view.description == "Foque no front-end."


def test_issue_mode_requires_issue(make_repo):
    repo = make_repo()
    svc = _issue_svc(repo)
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"mode": "issue", "description": "sem issue"})
    assert excinfo.value.code == "issue_required"


def test_issue_mode_rejects_issue_outside_allowlist(make_repo):
    repo = make_repo()
    gh = FakeIssueGh()
    svc = _issue_svc(repo, gh=gh)
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"mode": "issue", "issue_key": "evil/out#1"})
    assert excinfo.value.code == "repo_not_allowed"
    assert gh.calls == []


def test_issue_mode_reports_unavailable_issue(make_repo):
    repo = make_repo()
    svc = _issue_svc(repo, gh=FakeIssueGh(error="gh_error"))
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"mode": "issue", "issue_key": f"{REPO}#42"})
    assert excinfo.value.code == "issue_unavailable"


def test_issue_mode_without_gh_is_explicit(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    svc = InvestigationService(repo, AuthStore(repo), provider=FakeAdapter())
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"mode": "issue", "issue_key": f"{REPO}#42"})
    assert excinfo.value.code == "gh_missing"


def test_invalid_mode_rejected(make_repo):
    repo = make_repo()
    svc = _issue_svc(repo)
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"mode": "magia", "description": "x"})
    assert excinfo.value.code == "invalid_mode"


def test_manual_mode_still_requires_description(make_repo):
    repo = make_repo()
    svc = _issue_svc(repo)
    ana = actor(repo, "ana")
    with pytest.raises(InvestigationRuleError) as excinfo:
        svc.run(ana, {"mode": "manual", "issue_key": f"{REPO}#42"})
    assert excinfo.value.code == "invalid_description"


def test_issue_request_preview_is_redacted_and_counts_comments(make_repo):
    repo = make_repo()
    adapter = FakeAdapter()
    svc = _issue_svc(repo, provider=adapter)
    ana = actor(repo, "ana")
    preview = svc.issue_request_preview(ana, f"{REPO}#42")
    assert preview["title"] == "Formulário de contato não valida telefone"
    assert preview["labels"] == ["bug", "site"]
    assert preview["comments_used"] == 1
    assert preview["comments_total"] == 2
    assert "ghp_" not in preview["body_excerpt"]
    assert preview["repo"] == REPO
    assert adapter.prompts == []
