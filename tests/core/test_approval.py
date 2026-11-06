import threading

import pytest

from forge_core.agents.approval import ApprovalLedger
from forge_core.tasks import TaskService


def _setup(make_repo, grants):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", "pessoa:ana", assignee_kind="agent", assignee_id="priv")
    ledger = ApprovalLedger(repo)
    for _ in range(grants):
        ledger.grant(t.id, "pessoa:chefe", "priv")
    return t, ledger


def test_reserve_is_single_use_and_replay_fails(make_repo):
    t, ledger = _setup(make_repo, 1)
    assert ledger.available(t.id, "priv") == 1
    gid = ledger.reserve(t.id, "priv", "agente:orchestrator")
    assert gid is not None and ledger.available(t.id, "priv") == 0
    assert ledger.reserve(t.id, "priv", "agente:orchestrator") is None  # replay/retry: exige nova aprovação
    ledger.grant(t.id, "pessoa:chefe", "priv")
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
    t = TaskService(repo).create_task("t", "p")
    ledger = ApprovalLedger(repo)
    ledger.grant(t.id, "pessoa:chefe", "x")
    ledger.reserve(t.id, "x", "agente:orchestrator")
    for sql in ("UPDATE approval_consumptions SET agent = 'y'", "DELETE FROM approval_consumptions"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            repo._conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE approval_consumptions SET agent = 'y'", "DELETE FROM approval_consumptions",
                                 "TRUNCATE approval_consumptions"])
def test_consumption_table_privileges_postgres(pg_env, sql):
    import psycopg

    writer, owner, _ = pg_env
    t = TaskService(writer).create_task("t", "p")
    ledger = ApprovalLedger(writer)
    ledger.grant(t.id, "pessoa:chefe", "x")
    ledger.reserve(t.id, "x", "agente:orchestrator")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner._run([(sql, ())])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])
