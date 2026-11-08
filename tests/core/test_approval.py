import threading

import pytest

from auth_helpers import actor
from forge_core.agents.approval import ApprovalLedger
from forge_core.auth.store import AuthStore, Principal
from forge_core.errors import ApprovalError, AuthenticationError, AuthorizationError
from forge_core.tasks import TaskService


def _setup(make_repo, grants):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(svc, "ana"), assignee_kind="agent", assignee_id="priv")
    ledger = ApprovalLedger(repo)
    for _ in range(grants):
        ledger.grant(t.id, actor(repo, "chefe"), "priv")
    return t, ledger


def test_reserve_is_single_use_and_replay_fails(make_repo):
    t, ledger = _setup(make_repo, 1)
    assert ledger.available(t.id, "priv") == 1
    gid = ledger.reserve(t.id, "priv", "agente:orchestrator")
    assert gid is not None and ledger.available(t.id, "priv") == 0
    assert ledger.reserve(t.id, "priv", "agente:orchestrator") is None  # replay/retry: exige nova aprovação
    ledger.grant(t.id, actor(ledger._repo, "chefe"), "priv")
    assert ledger.reserve(t.id, "priv", "agente:orchestrator") not in (None, gid)


def test_reservation_is_for_that_task_and_agent(make_repo):
    t, ledger = _setup(make_repo, 1)
    assert ledger.reserve(t.id, "outro", "agente:orchestrator") is None
    assert ledger.reserve("outra-tarefa", "priv", "agente:orchestrator") is None


def _race(make_repo, grants):
    t, ledger0 = _setup(make_repo, grants)
    barrier = threading.Barrier(2)

    def hook():
        try:
            barrier.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass

    results = []

    def run():
        ledger = ApprovalLedger(make_repo())  # conexão independente por thread
        ledger._after_candidate_read = hook
        results.append(ledger.reserve(t.id, "priv", "agente:orchestrator"))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not any(th.is_alive() for th in threads)
    return t, ledger0, results


def test_concurrent_reserve_of_one_grant_exactly_one_wins(make_repo):
    t, ledger, results = _race(make_repo, 1)
    assert sorted(r is None for r in results) == [False, True], results
    assert ledger.available(t.id, "priv") == 0
    n = ledger._repo.fetch("SELECT COUNT(*) FROM approval_consumptions")[0][0]
    assert n == 1


def test_concurrent_reserve_of_two_grants_gets_distinct_grants(make_repo):
    t, ledger, results = _race(make_repo, 2)
    assert None not in results and len(set(results)) == 2
    assert ledger.available(t.id, "priv") == 0


def test_consumption_is_audited_with_grant_id(make_repo):
    t, ledger = _setup(make_repo, 1)
    gid = ledger.reserve(t.id, "priv", "agente:orchestrator")
    last = ledger._repo.list_audit()[-1]
    assert (last.action, last.result) == ("approval.consumed", f"ok: agent=priv grant={gid}")


def test_consumption_table_is_append_only_sqlite(tmp_path):
    import sqlite3

    from forge_core.storage import open_repository

    repo = open_repository(f"sqlite:///{tmp_path / 'a.db'}")
    t = TaskService(repo).create_task("t", actor(repo, "ana"))
    ledger = ApprovalLedger(repo)
    ledger.grant(t.id, actor(repo, "chefe"), "x")
    ledger.reserve(t.id, "x", "agente:orchestrator")
    for sql in ("UPDATE approval_consumptions SET agent = 'y'", "DELETE FROM approval_consumptions"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            repo._conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE approval_consumptions SET agent = 'y'", "DELETE FROM approval_consumptions",
                                 "TRUNCATE approval_consumptions"])
def test_consumption_table_privileges_postgres(pg_env, sql):
    import psycopg

    writer, owner, _ = pg_env
    t = TaskService(writer).create_task("t", actor(writer, "ana"))
    ledger = ApprovalLedger(writer)
    ledger.grant(t.id, actor(writer, "chefe"), "x")
    ledger.reserve(t.id, "x", "agente:orchestrator")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner._run([(sql, ())])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])


def test_text_cannot_stand_in_for_a_person(make_repo):
    t, ledger = _setup(make_repo, 0)
    with pytest.raises(ApprovalError, match="principal_missing"):
        ledger.grant(t.id, "pessoa:chefe", "priv")
    with pytest.raises(ApprovalError, match="principal_missing"):
        ledger.grant(t.id, object(), "priv")
    assert ledger.available(t.id, "priv") == 0


def test_principal_cannot_be_built_by_the_caller(make_repo):
    with pytest.raises(AuthenticationError, match="principal_forged"):
        Principal("gh:1003", "chefe", "sessao-inventada")


def test_editor_without_approver_role_cannot_grant(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(svc, "ana"), assignee_kind="agent", assignee_id="priv")
    with pytest.raises(ApprovalError, match="forbidden"):
        ApprovalLedger(repo).grant(t.id, actor(repo, "bia"), "priv")


def test_self_approval_is_refused_even_with_the_approver_role(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(svc, "ana"), assignee_kind="agent", assignee_id="priv")
    AuthStore(repo).grant_role(actor(repo, "dona"), 1001, "approver")
    with pytest.raises(ApprovalError, match="self_approval"):
        ApprovalLedger(repo).grant(t.id, actor(repo, "ana"), "priv")
    assert ApprovalLedger(repo).available(t.id, "priv") == 0


def test_revoked_approver_grant_does_not_release_reservation(make_repo):
    t, ledger = _setup(make_repo, 1)
    dona = actor(ledger._repo, "dona")
    grant_row = ledger._repo.fetch("SELECT id FROM role_grants WHERE identity_id = 'gh:1003'")[0][0]
    AuthStore(ledger._repo).revoke_role(dona, grant_row)
    assert ledger.available(t.id, "priv") == 0
    assert ledger.reserve(t.id, "priv", "agente:orchestrator") is None


def test_approval_is_bound_to_the_approved_version(make_repo):
    t, ledger = _setup(make_repo, 1)
    TaskService(ledger._repo).update_task(t.id, actor(ledger._repo, "ana"), 1, title="mudou")
    assert ledger.available(t.id, "priv") == 0
    assert ledger.reserve(t.id, "priv", "agente:orchestrator") is None


def test_legacy_textual_authorship_fails_closed(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(svc, "ana"), assignee_kind="agent", assignee_id="priv")
    repo.fetch("SELECT 1")
    cur = repo._conn.cursor()
    cur.execute(repo._q("INSERT INTO task_history (task_id, status, actor, at) VALUES (?, ?, ?, ?)"),
                (t.id, "pending", "pessoa:antiga", "2026-01-01T00:00:00+00:00"))
    repo._conn.commit()
    with pytest.raises(ApprovalError, match="untrusted_authorship"):
        ApprovalLedger(repo).grant(t.id, actor(repo, "chefe"), "priv")


def test_authorization_error_is_sanitized(make_repo):
    repo = make_repo()
    with pytest.raises(AuthorizationError, match="^forbidden$"):
        AuthStore(repo).require(actor(repo, "solta"), "approver")
