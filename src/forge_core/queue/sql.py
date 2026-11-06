"""Fila de jobs persistida no banco (ADR-002/ADR-004), sobre SqlRepository.

Entrega "pelo menos uma vez": o handler precisa ser idempotente. Toda transição grava auditoria na
mesma transação. O payload fica guardado como veio e NUNCA vai para auditoria ou logs: não coloque
segredos nele, use referências.

Fencing: cada claim gera um `claim_token` aleatório. complete/fail/heartbeat só valem com o token do
claim vigente e com o lease ainda válido; senão são recusados e a recusa é auditada.
Erros: run_once grava só o tipo da exceção do handler; a mensagem só entra se for um `JobFailure`
(explícito), e mesmo assim passa por redact().
"""
from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from ..config import Settings, require_automation_enabled
from ..errors import JobFailure, JobStateError
from ..extension.queue import Job, JobStatus
from ..logging import redact
from ..storage.sql import SqlRepository

_COLS = ("id, kind, payload, status, idempotency_key, attempts, max_attempts, run_at, lease_until, "
         "last_error, cancel_requested, created_at, updated_at")
_FMT = "%Y-%m-%dT%H:%M:%S.%f+00:00"  # largura fixa: comparação de texto = comparação de tempo
_MAX_ERROR = 2000


def _job(row) -> Job:
    r = list(row)
    r[2] = json.loads(r[2])
    r[10] = bool(r[10])
    return Job(*r)


_COLS_TOKEN = _COLS + ", claim_token"


class SqlJobQueue:
    def __init__(
        self,
        repo: SqlRepository,
        settings: Settings | None = None,
        max_attempts: int = 5,
        backoff_base: float = 30,
        backoff_cap: float = 3600,
        lease_seconds: float = 300,
        clock: Callable[[], datetime] | None = None,
        jitter: Callable[[float], float] = lambda d: d,
    ):
        self._repo, self._settings = repo, settings
        self.max_attempts, self.backoff_base, self.backoff_cap = max_attempts, backoff_base, backoff_cap
        self.lease_seconds, self._clock, self._jitter = lease_seconds, clock or (lambda: datetime.now(timezone.utc)), jitter

    def _now(self) -> datetime:
        return self._clock()

    @staticmethod
    def _ts(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime(_FMT)

    def backoff(self, attempts: int) -> float:
        """Atraso após a tentativa `attempts` (1-based): base * 2^(n-1), limitado ao teto."""
        return self._jitter(min(self.backoff_cap, self.backoff_base * 2 ** (attempts - 1)))

    def enqueue(self, kind: str, payload: dict, actor: str,
                idempotency_key: str | None = None, max_attempts: int | None = None) -> Job:
        """Permitido mesmo com a automação desligada (ADR-006 bloqueia só o consumo)."""
        if idempotency_key:
            existing = self._by_key(idempotency_key)
            if existing:
                self._repo.record_audit(actor, "job.enqueue", f"job:{existing.id}", f"duplicate: kind={kind}")
                return existing
        job_id, now = str(uuid.uuid4()), self._ts(self._now())
        try:
            with self._repo.transaction() as tx:
                tx.execute(
                    f"INSERT INTO jobs ({_COLS}) VALUES (?, ?, ?, ?, ?, 0, ?, ?, NULL, NULL, 0, ?, ?)",
                    (job_id, kind, json.dumps(payload), JobStatus.QUEUED, idempotency_key,
                     max_attempts or self.max_attempts, now, now, now),
                )
                tx.audit(actor, "job.enqueue", f"job:{job_id}", f"ok: kind={kind}")
        except Exception:
            existing = self._by_key(idempotency_key) if idempotency_key else None
            if existing is None:
                raise
            return existing  # corrida entre dois enqueue com a mesma chave
        return self.get_job(job_id)  # type: ignore[return-value]

    def claim(self, actor: str, kinds: list[str] | None = None) -> Job | None:
        """Pega o próximo job pronto. Postgres: FOR UPDATE SKIP LOCKED. SQLite: BEGIN IMMEDIATE."""
        if self._settings is not None:
            require_automation_enabled(self._settings)
        now_dt = self._now()
        now, lease = self._ts(now_dt), self._ts(now_dt + timedelta(seconds=self.lease_seconds))
        token = secrets.token_urlsafe(16)
        kind_sql = f"AND kind IN ({','.join('?' * len(kinds))})" if kinds else ""
        lock = "FOR UPDATE SKIP LOCKED" if self._repo.dialect == "postgres" else ""
        with self._repo.transaction() as tx:
            self._reap(tx, now, actor)
            rows = tx.execute(
                "UPDATE jobs SET status = 'running', attempts = attempts + 1, lease_until = ?, claim_token = ?, "
                "updated_at = ? WHERE id = (SELECT id FROM jobs WHERE status = 'queued' AND run_at <= ? "
                f"{kind_sql} ORDER BY run_at, id LIMIT 1 {lock}) RETURNING {_COLS_TOKEN}",
                (lease, token, now, now, *(kinds or [])),
            ).fetchall()
            if not rows:
                return None
            job = _job(rows[0])
            tx.audit(actor, "job.claim", f"job:{job.id}", f"ok: attempt {job.attempts}/{job.max_attempts}")
            return job

    def _reap(self, tx, now: str, actor: str) -> None:
        """Job com lease vencido (consumidor caiu): volta para a fila ou falha se esgotou tentativas."""
        rows = tx.execute(
            "SELECT id, attempts, max_attempts, cancel_requested FROM jobs "
            "WHERE status = 'running' AND lease_until < ?", (now,)).fetchall()
        for job_id, attempts, max_attempts, cancel in rows:
            if cancel:
                status, action, result = JobStatus.CANCELLED, "job.cancel", "ok: lease vencido com cancelamento"
            elif attempts >= max_attempts:
                status, action, result = JobStatus.FAILED, "job.fail", "error: lease vencido, tentativas esgotadas"
            else:
                status, action, result = JobStatus.QUEUED, "job.retry", "error: lease vencido"
            tx.execute(
                "UPDATE jobs SET status = ?, run_at = ?, lease_until = NULL, claim_token = NULL, "
                "last_error = ?, updated_at = ? "
                "WHERE id = ? AND status = 'running'",
                (status, now, "lease vencido", now, job_id))
            tx.audit(actor, action, f"job:{job_id}", result)

    def _mutate(self, job_id: str, action: str, actor: str, fn) -> Job:
        """Carrega o job com lock, aplica `fn` e audita. Recusas também são auditadas."""
        lock = " FOR UPDATE" if self._repo.dialect == "postgres" else ""
        err: Exception | None = None
        with self._repo.transaction() as tx:
            rows = tx.execute(f"SELECT {_COLS_TOKEN} FROM jobs WHERE id = ?{lock}", (job_id,)).fetchall()
            if not rows:
                err = KeyError(job_id)
            else:
                try:
                    fn(tx, _job(rows[0]), self._ts(self._now()))
                except JobStateError as exc:
                    err = exc
        if err is not None:
            self._repo.record_audit(actor, action, f"job:{job_id}", f"error: {err}")
            raise err
        return self.get_job(job_id)  # type: ignore[return-value]

    @staticmethod
    def _set(tx, job_id: str, now: str, **cols) -> None:
        cols["updated_at"] = now
        names = ", ".join(f"{k} = ?" for k in cols)
        tx.execute(f"UPDATE jobs SET {names} WHERE id = ?", (*cols.values(), job_id))

    def _check_claim(self, tx, job: Job, claim_token: str, now: str) -> None:
        if job.status != JobStatus.RUNNING:
            raise JobStateError(f"job {job.id} não está running ({job.status})")
        if not job.claim_token or not secrets.compare_digest(job.claim_token, claim_token or ""):
            raise JobStateError(f"job {job.id}: claim_token não é o do claim vigente")
        if job.lease_until is None or job.lease_until <= now:
            raise JobStateError(f"job {job.id}: lease vencido")

    def _guarded_set(self, tx, job_id: str, token: str, now: str, **cols) -> None:
        """UPDATE ... WHERE id = ? AND claim_token = ? AND lease_until > now (defesa extra ao lock da linha)."""
        cols["updated_at"] = now
        names = ", ".join(f"{k} = ?" for k in cols)
        cur = tx.execute(
            f"UPDATE jobs SET {names} WHERE id = ? AND claim_token = ? AND lease_until > ?",
            (*cols.values(), job_id, token, now))
        if cur.rowcount != 1:
            raise JobStateError(f"job {job_id}: claim inválido ou lease vencido")

    def complete(self, job_id: str, actor: str, claim_token: str) -> Job:
        def fn(tx, job: Job, now: str):
            self._check_claim(tx, job, claim_token, now)
            self._guarded_set(tx, job_id, claim_token, now,
                              status=JobStatus.SUCCEEDED, lease_until=None, claim_token=None)
            tx.audit(actor, "job.complete", f"job:{job_id}", f"ok: attempt {job.attempts}")
        return self._mutate(job_id, "job.complete", actor, fn)

    def heartbeat(self, job_id: str, actor: str, claim_token: str) -> Job:
        """Renova o lease do claim vigente. Só recusas são auditadas (heartbeat é frequente)."""
        def fn(tx, job: Job, now: str):
            self._check_claim(tx, job, claim_token, now)
            lease = self._ts(self._now() + timedelta(seconds=self.lease_seconds))
            self._guarded_set(tx, job_id, claim_token, now, lease_until=lease)
        return self._mutate(job_id, "job.heartbeat", actor, fn)

    def fail(self, job_id: str, error: str, actor: str, claim_token: str, retryable: bool = True) -> Job:
        err = redact(error)[:_MAX_ERROR]

        def fn(tx, job: Job, now: str):
            self._check_claim(tx, job, claim_token, now)
            if job.cancel_requested:
                status, action, extra = JobStatus.CANCELLED, "job.cancel", {}
            elif not retryable or job.attempts >= job.max_attempts:
                status, action, extra = JobStatus.FAILED, "job.fail", {}
            else:
                run_at = self._ts(self._now() + timedelta(seconds=self.backoff(job.attempts)))
                status, action, extra = JobStatus.QUEUED, "job.retry", {"run_at": run_at}
            self._guarded_set(tx, job_id, claim_token, now, status=status, lease_until=None,
                              claim_token=None, last_error=err, **extra)
            tx.audit(actor, action, f"job:{job_id}", f"error: {err}")
        return self._mutate(job_id, "job.fail", actor, fn)

    def cancel(self, job_id: str, actor: str) -> Job:
        """queued vira cancelled. running só recebe o pedido (cooperativo). Estado terminal: erro."""
        def fn(tx, job: Job, now: str):
            if job.status == JobStatus.QUEUED:
                self._set(tx, job_id, now, status=JobStatus.CANCELLED)
                tx.audit(actor, "job.cancel", f"job:{job_id}", "ok")
            elif job.status == JobStatus.RUNNING:
                self._set(tx, job_id, now, cancel_requested=1)
                tx.audit(actor, "job.cancel", f"job:{job_id}", "ok: cancelamento solicitado")
            else:
                raise JobStateError(f"job {job_id} já terminou ({job.status})")
        return self._mutate(job_id, "job.cancel", actor, fn)

    def requeue(self, job_id: str, actor: str) -> Job:
        """Reprocessamento manual de um job em falha definitiva: zera as tentativas."""
        def fn(tx, job: Job, now: str):
            if job.status != JobStatus.FAILED:
                raise JobStateError(f"só job failed pode ser reenfileirado ({job.status})")
            self._set(tx, job_id, now, status=JobStatus.QUEUED, attempts=0, run_at=now,
                      lease_until=None, cancel_requested=0)
            tx.audit(actor, "job.requeue", f"job:{job_id}", "ok")
        return self._mutate(job_id, "job.requeue", actor, fn)

    def get_job(self, job_id: str) -> Job | None:
        rows = self._repo.fetch(f"SELECT {_COLS} FROM jobs WHERE id = ?", (job_id,))
        return _job(rows[0]) if rows else None

    def _by_key(self, key: str) -> Job | None:
        rows = self._repo.fetch(f"SELECT {_COLS} FROM jobs WHERE idempotency_key = ?", (key,))
        return _job(rows[0]) if rows else None

    def list_jobs(self, status: str | None = None) -> list[Job]:
        where, params = ("WHERE status = ?", (status,)) if status else ("", ())
        return [_job(r) for r in self._repo.fetch(f"SELECT {_COLS} FROM jobs {where} ORDER BY created_at, id", params)]

    def run_once(self, handler: Callable[[Job], None], actor: str, kinds: list[str] | None = None) -> Job | None:
        job = self.claim(actor, kinds)
        if job is None:
            return None
        try:
            handler(job)
        except JobFailure as exc:  # mensagem explícita e segura, ainda assim redigida em fail()
            return self.fail(job.id, f"JobFailure: {exc}", actor, job.claim_token, retryable=exc.retryable)
        except Exception as exc:  # código de terceiros: só o tipo, nunca a mensagem (pode ecoar o payload)
            return self.fail(job.id, type(exc).__name__, actor, job.claim_token)
        return self.complete(job.id, actor, job.claim_token)
