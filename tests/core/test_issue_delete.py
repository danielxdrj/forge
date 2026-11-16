"""Exclusão de issue (GitHub + registros locais): confirmação exata, fallback, limpeza local."""
from __future__ import annotations

import subprocess

import pytest
from auth_helpers import actor

from forge_core.auth.store import AuthStore
from forge_core.draft.github_gh import GhCli
from forge_core.errors import AuthorizationError
from forge_core.issues.delete import IssueDeleteError, IssueDeleteService
from forge_core.issues.store import upsert
from forge_core.storage.drafts import (
    insert_draft,
    insert_task_link,
    list_drafts_for_task,
    list_task_links,
)
from forge_core.storage.seed import seed_allowed_repos
from forge_core.tasks.service import TaskService

REPO = "ferreiraeborzone/site"
NUMBER = 9


def _runner(*, forbidden=False, close_fails=False):
    def run(argv, **kwargs):
        cmd = argv[1:]
        if cmd[0] == "api" and cmd[1].startswith("repos/") and cmd[1].endswith(f"/issues/{NUMBER}"):
            return subprocess.CompletedProcess(argv, 0, stdout=b"I_nodeid123\n", stderr=b"")
        if cmd[:2] == ["api", "graphql"] and "deleteIssue" in " ".join(cmd):
            if forbidden:
                return subprocess.CompletedProcess(
                    argv, 1, stdout=b"", stderr=b"HTTP 403: Resource not accessible by integration",
                )
            return subprocess.CompletedProcess(argv, 0, stdout=b"{}", stderr=b"")
        if cmd[:2] == ["issue", "close"]:
            if close_fails:
                return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"some error")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
    return run


def _seed_completed_issue(repo):
    upsert(repo, {
        "repo": REPO, "number": NUMBER, "title": "fix login", "body": "x",
        "labels": {"names": ["Bug"]}, "prs": [], "closed_at": None,
        "url": f"https://github.com/{REPO}/issues/{NUMBER}",
    })


def test_delete_requires_exact_confirmation(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    gh = GhCli(runner=_runner())
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    with pytest.raises(IssueDeleteError) as excinfo:
        svc.delete(owner, "ferreiraeborzone", "site", NUMBER, "errado")
    assert excinfo.value.code == "confirm_mismatch"


def test_delete_requires_owner_role(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    gh = GhCli(runner=_runner())
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    ana = actor(repo, "ana")  # editor, não owner
    with pytest.raises(AuthorizationError):
        svc.delete(ana, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}")


def test_delete_succeeds_and_purges_completed_issue_cache(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    _seed_completed_issue(repo)
    gh = GhCli(runner=_runner())
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    result = svc.delete(owner, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}")
    assert result.mode == "deleted"
    assert repo.fetch(
        "SELECT 1 FROM completed_issues WHERE repo = ? AND number = ?", (REPO, NUMBER),
    ) == []
    actions = [a.action for a in repo.list_audit()]
    assert "issue.delete" in actions


def test_delete_forbidden_without_fallback_returns_clear_error(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    gh = GhCli(runner=_runner(forbidden=True))
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    with pytest.raises(IssueDeleteError) as excinfo:
        svc.delete(owner, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}")
    assert excinfo.value.code == "issue_delete_forbidden"


def test_delete_forbidden_with_fallback_close_marks_not_planned(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    _seed_completed_issue(repo)
    gh = GhCli(runner=_runner(forbidden=True))
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    result = svc.delete(
        owner, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}", fallback="close",
    )
    assert result.mode == "closed"
    assert repo.fetch(
        "SELECT 1 FROM completed_issues WHERE repo = ? AND number = ?", (REPO, NUMBER),
    ) == []


def test_delete_purges_draft_and_task_links(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    gh = GhCli(runner=_runner())
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    ana = actor(repo, "ana")
    tasks = TaskService(repo)
    task = tasks.create_task("rascunho issue", ana)
    insert_draft(
        repo, task_id=task.id, repo_name=REPO, body_md="x", tipo="", prioridade="",
        size="", preview_hash="h", created_by=ana.identity_id,
    )
    insert_task_link(
        repo, task_id=task.id, kind="issue", repo_name=REPO,
        url=f"https://github.com/{REPO}/issues/{NUMBER}", number=NUMBER,
    )
    svc.delete(owner, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}")
    assert list_drafts_for_task(repo, task.id) == []
    assert list_task_links(repo, task.id) == []


def test_delete_unlinks_notes_by_default_and_purges_with_flag(make_repo):
    from forge_core.notes.service import NoteService

    repo = make_repo()
    seed_allowed_repos(repo)
    gh = GhCli(runner=_runner())
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    notes = NoteService(repo, AuthStore(repo))
    note = notes.create(owner, {"issue_key": f"{REPO}#{NUMBER}", "title": "t", "body": "b"})
    svc.delete(owner, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}")
    reloaded = notes.get_note(owner, note.id)
    assert reloaded.issue_key is None


def test_delete_with_purge_notes_flag_removes_note(make_repo):
    from forge_core.notes.service import NoteRuleError, NoteService

    repo = make_repo()
    seed_allowed_repos(repo)
    gh = GhCli(runner=_runner())
    svc = IssueDeleteService(repo, AuthStore(repo), gh)
    owner = actor(repo, "dona")
    notes = NoteService(repo, AuthStore(repo))
    note = notes.create(owner, {"issue_key": f"{REPO}#{NUMBER}", "title": "t", "body": "b"})
    svc.delete(owner, "ferreiraeborzone", "site", NUMBER, f"{REPO}#{NUMBER}", purge_notes=True)
    with pytest.raises(NoteRuleError):
        notes.get_note(owner, note.id)
