"""Notas manuais por issue: migração, CRUD e auditoria sem o corpo."""
from forge_core.notes.service import NoteRuleError, NoteService
from forge_core.storage.migrate import pending_migrations
from forge_core.storage.seed import seed_allowed_repos
from forge_core.auth.store import AuthStore
from auth_helpers import actor

SENTINEL = "SENTINELA_NOTA_NAO_LOGAR_<script>alert(1)</script>"
ISSUE = "ferreiraeborzone/site#9"


def _svc(repo):
    seed_allowed_repos(repo)
    return NoteService(repo, AuthStore(repo))


def test_0016_listed_for_both_dialects_and_table_exists(make_repo):
    sqlite = [p.stem for p in pending_migrations("sqlite")]
    postgres = [p.stem for p in pending_migrations("postgres")]
    assert any(s.startswith("0016_investigation_notes") for s in sqlite)
    assert any(s.startswith("0016_investigation_notes") for s in postgres)
    repo = make_repo()
    repo.fetch("SELECT id, issue_key, title, body, created_by, created_at, updated_at FROM investigation_notes LIMIT 0")


def test_create_list_update_delete_and_audit_omits_body(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    ana = actor(repo, "ana")
    created = svc.create(ana, {"issue_key": ISSUE, "title": "Hipótese", "body": SENTINEL})
    assert created.title == "Hipótese"
    assert created.body == SENTINEL
    listed = svc.list_notes(ana, ISSUE)
    assert len(listed) == 1
    assert listed[0].id == created.id
    json_list = listed[0].as_json(include_body=False)
    assert "body" not in json_list
    assert json_list["size"] == len(SENTINEL.encode("utf-8"))
    updated = svc.update(ana, created.id, {"title": "Hipótese 2", "body": SENTINEL + "!"})
    assert updated.title == "Hipótese 2"
    svc.delete(ana, created.id)
    assert svc.list_notes(ana, ISSUE) == []
    dump = repr(repo.list_audit())
    assert SENTINEL not in dump
    actions = [a.action for a in repo.list_audit()]
    assert "note.create" in actions
    assert "note.update" in actions
    assert "note.delete" in actions
    for entry in repo.list_audit():
        if entry.action.startswith("note."):
            assert entry.target.startswith("note:")
            assert "bytes=" in entry.result


def test_rejects_repo_outside_allowlist_and_anon(make_repo):
    repo = make_repo()
    svc = _svc(repo)
    ana = actor(repo, "ana")
    try:
        svc.create(ana, {"issue_key": "evil/out#1", "title": "x", "body": "y"})
        assert False, "expected NoteRuleError"
    except NoteRuleError as exc:
        assert exc.code == "repo_not_allowed"
    solta = actor(repo, "solta")
    try:
        svc.create(solta, {"issue_key": ISSUE, "title": "x", "body": "y"})
        assert False, "expected forbidden"
    except Exception as exc:
        assert "forbidden" in str(exc).lower() or type(exc).__name__ == "AuthorizationError"
