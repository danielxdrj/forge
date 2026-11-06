from datetime import datetime, timedelta, timezone

import pytest

from forge_core.config import load_settings
from forge_core.errors import AutomationDisabledError, JobStateError
from forge_core.queue import SqlJobQueue
from forge_core.storage import open_repository

from conftest import PG_URL

pg = pytest.mark.skipif(not PG_URL, reason="FORGE_DATABASE_URL não definida")
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    repo = open_repository(f"sqlite:///{tmp_path / 'q.db'}")
    return SqlJobQueue(repo, clock=clock), repo, clock, tmp_path


def actions(repo):
    return [a.action for a in repo.list_audit()]


def test_success_flow_and_audit(env):
    q, repo, _, _ = env
    q.enqueue("demo", {"x": 1}, "pessoa:ana")
    seen = []
    job = q.run_once(lambda j: seen.append(j.payload), "agente:worker")
    assert seen == [{"x": 1}] and job.status == "succeeded" and job.attempts == 1
    assert actions(repo) == ["job.enqueue", "job.claim", "job.complete"]
    assert q.run_once(lambda j: None, "agente:worker") is None


def test_transient_failure_retries_with_backoff_then_succeeds(env):
    q, repo, clock, _ = env
    q.enqueue("demo", {}, "pessoa:ana")

    def boom(job):
        raise RuntimeError("falha transitória")

    j = q.run_once(boom, "w")
    assert j.status == "queued" and j.attempts == 1 and "falha transitória" in j.last_error
    assert q.claim("w") is None  # ainda em backoff
    clock.advance(29)
    assert q.claim("w") is None
    clock.advance(1)
    j = q.run_once(lambda job: None, "w")
    assert j.status == "succeeded" and j.attempts == 2
    assert "job.retry" in actions(repo)


def test_backoff_doubles_and_is_capped(env):
    q, *_ = env
    assert [q.backoff(n) for n in (1, 2, 3, 7, 8, 20)] == [30, 60, 120, 1920, 3600, 3600]


def test_permanent_failure_after_max_attempts(env):
    q, repo, clock, _ = env
    q.enqueue("demo", {}, "pessoa:ana", max_attempts=3)
    for _ in range(3):
        clock.advance(4000)
        j = q.run_once(lambda job: 1 / 0, "w")
    assert j.status == "failed" and j.attempts == 3 and "ZeroDivisionError" in j.last_error
    clock.advance(4000)
    assert q.claim("w") is None
    assert actions(repo).count("job.retry") == 2 and actions(repo)[-1] == "job.fail"


def test_non_retryable_fails_immediately(env):
    q, *_ = env
    j = q.enqueue("demo", {}, "pessoa:ana")
    q.claim("w")
    assert q.fail(j.id, "dado inválido", "w", retryable=False).status == "failed"


def test_requeue_failed_job(env):
    q, repo, _, _ = env
    j = q.enqueue("demo", {}, "pessoa:ana")
    q.claim("w")
    q.fail(j.id, "x", "w", retryable=False)
    r = q.requeue(j.id, "pessoa:ana")
    assert r.status == "queued" and r.attempts == 0
    assert q.run_once(lambda job: None, "w").status == "succeeded"
    with pytest.raises(JobStateError):
        q.requeue(j.id, "pessoa:ana")
    assert repo.list_audit()[-1].result.startswith("error")


def test_idempotency_key_prevents_duplicates(env):
    q, repo, _, _ = env
    a = q.enqueue("demo", {"n": 1}, "pessoa:ana", idempotency_key="evento-1")
    b = q.enqueue("demo", {"n": 2}, "pessoa:ana", idempotency_key="evento-1")
    assert a.id == b.id and len(q.list_jobs()) == 1
    assert repo.list_audit()[-1].result.startswith("duplicate")


def test_two_connections_never_claim_the_same_job(env):
    q1, repo1, clock, tmp = env
    repo2 = open_repository(f"sqlite:///{tmp / 'q.db'}")
    q2 = SqlJobQueue(repo2, clock=clock)
    q1.enqueue("demo", {}, "pessoa:ana")
    q1.enqueue("demo", {}, "pessoa:ana")
    a, b, c = q1.claim("w1"), q2.claim("w2"), q2.claim("w2")
    assert a.id != b.id and c is None


def test_expired_lease_returns_job_and_counts_attempt(env):
    q, repo, clock, _ = env
    q.enqueue("demo", {}, "pessoa:ana", max_attempts=2)
    q.claim("w")
    assert q.claim("w2") is None  # lease ainda válido
    clock.advance(301)
    j = q.claim("w2")
    assert j.attempts == 2
    clock.advance(301)
    assert q.claim("w3") is None and q.list_jobs("failed")[0].last_error == "lease vencido"


def test_late_complete_after_lease_loss_is_refused(env):
    q, _, clock, _ = env
    j = q.enqueue("demo", {}, "pessoa:ana")
    q.claim("w")
    clock.advance(301)
    q.claim("w2")
    q.complete(j.id, "w2")
    with pytest.raises(JobStateError):
        q.complete(j.id, "w")


def test_cancel_queued_running_and_terminal(env):
    q, repo, _, _ = env
    a = q.enqueue("demo", {}, "pessoa:ana")
    assert q.cancel(a.id, "pessoa:ana").status == "cancelled"
    assert q.claim("w") is None
    b = q.enqueue("demo", {}, "pessoa:ana")
    q.claim("w")
    assert q.cancel(b.id, "pessoa:ana").cancel_requested is True
    assert q.fail(b.id, "interrompido", "w").status == "cancelled"  # cooperativo: sem retry
    with pytest.raises(JobStateError):
        q.cancel(b.id, "pessoa:ana")
    with pytest.raises(KeyError):
        q.cancel("nao-existe", "pessoa:ana")


def test_status_query_and_kind_filter(env):
    q, *_ = env
    q.enqueue("a", {}, "p")
    q.enqueue("b", {}, "p")
    assert q.claim("w", kinds=["b"]).kind == "b"
    assert [j.kind for j in q.list_jobs("queued")] == ["a"]
    assert q.get_job("x") is None


def test_error_is_redacted_and_payload_not_audited(env):
    q, repo, _, _ = env
    j = q.enqueue("demo", {"ref": "valor-do-payload"}, "pessoa:ana")
    q.claim("w")
    out = q.fail(j.id, "falhou: Authorization: Bearer seg redo", "w", retryable=False)
    dump = repr(out.last_error) + repr(repo.list_audit())
    assert "seg" not in dump and "redo" not in dump and "valor-do-payload" not in dump


def test_automation_disabled_blocks_claim_but_not_enqueue(tmp_path):
    off = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AUTOMATION_ENABLED": "false"})
    q = SqlJobQueue(open_repository(f"sqlite:///{tmp_path / 'q.db'}"), settings=off)
    q.enqueue("demo", {}, "pessoa:ana")
    with pytest.raises(AutomationDisabledError):
        q.claim("w")
    assert q.list_jobs("queued")


def test_jobs_survive_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'q.db'}"
    j = SqlJobQueue(open_repository(url)).enqueue("demo", {"a": 1}, "pessoa:ana")
    assert SqlJobQueue(open_repository(url)).get_job(j.id).payload == {"a": 1}


@pg
def test_postgres_skip_locked_gives_different_jobs(pg_env):
    writer, _, new_writer = pg_env
    q1 = SqlJobQueue(writer)
    q2 = SqlJobQueue(new_writer())
    q1.enqueue("demo", {}, "p")
    q1.enqueue("demo", {}, "p")
    holder = new_writer()._conn.cursor()  # consumidor A segura a linha travada, sem commit
    holder.execute("SELECT id FROM jobs WHERE status = 'queued' ORDER BY run_at, id LIMIT 1 FOR UPDATE")
    locked = holder.fetchone()[0]
    got = q2.claim("w2")
    assert got is not None and got.id != locked
    assert q2.claim("w2") is None  # a outra linha segue travada: SKIP LOCKED não bloqueia nem duplica
    holder.connection.rollback()


@pg
def test_postgres_retry_and_writer_cannot_delete_jobs(pg_env):
    import psycopg

    writer, _, _ = pg_env
    q = SqlJobQueue(writer, backoff_base=0)
    q.enqueue("demo", {}, "p", max_attempts=2)
    assert q.run_once(lambda j: 1 / 0, "w").status == "queued"
    assert q.run_once(lambda j: 1 / 0, "w").status == "failed"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([("DELETE FROM jobs", ())])
