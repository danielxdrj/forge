"""Despacho pela fila: autorização no enqueue, vínculo persistido, revalidação na execução. Sem bearer no job."""
import json

import pytest

from auth_helpers import actor
from forge_core.agents import Orchestrator, default_registry
from forge_core.auth.store import AuthStore
from forge_core.errors import AuthorizationError
from forge_core.queue import SqlJobQueue
from forge_core.tasks import TaskService, TaskStatus as S


def _env(make_repo):
    repo = make_repo()
    orch = Orchestrator(repo, default_registry())
    return repo, TaskService(repo), orch, SqlJobQueue(repo)


def _task(svc, repo):
    return svc.create_task("Tarefa", actor(repo, "ana"), objective="faça",
                           assignee_kind="agent", assignee_id="echo")


def test_enqueue_and_job_dispatch_as_the_human_who_queued(make_repo):
    repo, svc, orch, q = _env(make_repo)
    t = _task(svc, repo)
    job = orch.enqueue(q, t.id, actor(repo, "ana"))
    assert job.kind == "orchestrate" and set(job.payload) == {"dispatch_id", "task_id"}
    assert job.payload["task_id"] == t.id
    raw = repo.fetch("SELECT payload FROM jobs WHERE id = ?", (job.id,))[0][0]
    dump = json.dumps(job.payload) + raw + repr(repo.list_audit())
    assert "tok-" not in dump and "access_token" not in dump
    done = q.run_once(orch.job_handler(), "sistema:fila")
    assert done.status == "succeeded"
    assert svc.get_task(t.id).status == S.IN_VALIDATION
    sid = repo.fetch("SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1")[0][0]
    assert repo.fetch("SELECT 1 FROM session_revocations WHERE session_id = ?", (sid,))


def test_enqueue_refuses_non_editor(make_repo):
    repo, svc, orch, q = _env(make_repo)
    t = _task(svc, repo)
    with pytest.raises(AuthorizationError, match="forbidden"):
        orch.enqueue(q, t.id, actor(repo, "chefe"))
    with pytest.raises(AuthorizationError, match="forbidden"):
        orch.enqueue(q, t.id, actor(repo, "solta"))
    assert q.list_jobs() == [] and repo.fetch("SELECT COUNT(*) FROM dispatch_requests")[0][0] == 0


def test_revocation_after_enqueue_fails_the_job_and_leaves_task_pending(make_repo):
    repo, svc, orch, q = _env(make_repo)
    t = _task(svc, repo)
    orch.enqueue(q, t.id, actor(repo, "ana"))
    gid = repo.fetch("SELECT id FROM role_grants WHERE identity_id = 'gh:1001' AND role = 'editor'")[0][0]
    AuthStore(repo).revoke_role(actor(repo, "dona"), gid)
    job = q.run_once(orch.job_handler(), "sistema:fila")
    assert job.status == "failed" and "forbidden" in job.last_error
    assert svc.get_task(t.id).status == S.PENDING and repo.fetch("SELECT COUNT(*) FROM agent_runs")[0][0] == 0


def test_version_change_after_enqueue_fails_the_job(make_repo):
    repo, svc, orch, q = _env(make_repo)
    t = _task(svc, repo)
    orch.enqueue(q, t.id, actor(repo, "ana"))
    svc.update_task(t.id, actor(repo, "ana"), 1, title="v2")
    job = q.run_once(orch.job_handler(), "sistema:fila")
    assert job.status == "failed" and "versao" in job.last_error
    assert svc.get_task(t.id).status == S.PENDING


def test_forged_dispatch_id_and_cross_task_payload_fail(make_repo):
    repo, svc, orch, q = _env(make_repo)
    t = _task(svc, repo)
    other = _task(svc, repo)
    q.enqueue("orchestrate", {"dispatch_id": "nao-existe", "task_id": t.id}, "gh:1001")
    job = q.run_once(orch.job_handler(), "sistema:fila")
    assert job.status == "failed" and "vinculo" in job.last_error
    real = orch.enqueue(q, t.id, actor(repo, "ana"))
    q.cancel(real.id, "teste")
    q.enqueue("orchestrate", {"dispatch_id": real.payload["dispatch_id"], "task_id": other.id},
              "gh:1001", idempotency_key="forjado")
    job2 = q.run_once(orch.handler(), "sistema:fila")
    assert job2.status == "failed" and "vinculo" in job2.last_error
    assert svc.get_task(t.id).status == S.PENDING and svc.get_task(other.id).status == S.PENDING


def test_job_payload_has_no_session_or_oauth_secret(make_repo):
    repo, svc, orch, q = _env(make_repo)
    t = _task(svc, repo)
    job = orch.enqueue(q, t.id, actor(repo, "ana"))
    row = repo.fetch("SELECT payload FROM jobs WHERE id = ?", (job.id,))[0][0]
    assert "token" not in row.lower() and "oauth" not in row.lower()
    assert "github" not in row.lower()
    req = repo.fetch("SELECT identity_id FROM dispatch_requests")[0][0]
    assert req == "gh:1001"
