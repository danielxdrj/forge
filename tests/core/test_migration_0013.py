import pytest

from forge_core.storage.drafts import DraftStorageError, insert_draft, insert_task_link, list_drafts_for_task, list_task_links
from forge_core.storage.migrate import pending_migrations
from forge_core.tasks import TaskService
from auth_helpers import actor


def test_0013_is_listed_for_both_dialects():
    sqlite = [p.stem for p in pending_migrations("sqlite")]
    postgres = [p.stem for p in pending_migrations("postgres")]
    assert any(s.startswith("0013_") for s in sqlite)
    assert any(s.startswith("0013_") for s in postgres)


def test_0013_tables_and_expires_at_exist(make_repo):
    repo = make_repo()
    repo.fetch("SELECT id, task_id, repo, body_md, tipo, prioridade, size, preview_hash, status, created_by, created_at, updated_at FROM drafts LIMIT 0")
    repo.fetch("SELECT id, task_id, kind, repo, number, url, board_item_id, created_at FROM task_links LIMIT 0")
    repo.fetch("SELECT expires_at FROM sessions LIMIT 0")


def test_draft_status_check_and_helpers(make_repo):
    repo = make_repo()
    ana = actor(repo, "ana")
    task = TaskService(repo).create_task("rascunho de teste", ana)
    rec = insert_draft(
        repo,
        task_id=task.id,
        repo_name="ferreiraeborzone/site",
        body_md="# oi",
        tipo="feat",
        prioridade="alta",
        size="M",
        preview_hash="abc",
        created_by=ana.identity_id,
    )
    assert rec.status == "rascunho"
    assert list_drafts_for_task(repo, task.id)[0].id == rec.id
    with pytest.raises(Exception):
        insert_draft(
            repo,
            task_id=task.id,
            repo_name="ferreiraeborzone/site",
            body_md="x",
            tipo="feat",
            prioridade="alta",
            size="M",
            preview_hash="abc",
            created_by=ana.identity_id,
            status="invalido",
        )
    repo._conn.rollback()


def test_task_links_unique_and_helpers(make_repo):
    repo = make_repo()
    ana = actor(repo, "ana")
    task = TaskService(repo).create_task("vincular", ana)
    link = insert_task_link(
        repo,
        task_id=task.id,
        kind="issue",
        repo_name="ferreiraeborzone/site",
        url="https://github.com/ferreiraeborzone/site/issues/1",
        number=1,
    )
    assert list_task_links(repo, task.id)[0].id == link.id
    with pytest.raises(Exception):
        insert_task_link(
            repo,
            task_id=task.id,
            kind="issue",
            repo_name="ferreiraeborzone/site",
            url="https://github.com/ferreiraeborzone/site/issues/1",
            number=1,
        )
    repo._conn.rollback()
    with pytest.raises(DraftStorageError, match="invalid_link_kind"):
        insert_task_link(
            repo, task_id=task.id, kind="wiki", repo_name="ferreiraeborzone/site", url="https://example.invalid"
        )
