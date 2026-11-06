"""Porta da fila de jobs (ADR-002). A implementação inicial é persistida no banco (FRG-40)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"  # falha definitiva: só sai daqui por requeue() manual
    CANCELLED = "cancelled"
    TERMINAL = (SUCCEEDED, FAILED, CANCELLED)


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    payload: dict[str, Any]
    status: str
    idempotency_key: str | None
    attempts: int
    max_attempts: int
    run_at: str
    lease_until: str | None
    last_error: str | None
    cancel_requested: bool
    created_at: str
    updated_at: str
    claim_token: str | None = None  # só preenchido pelo retorno de claim()


class JobQueue(Protocol):
    def enqueue(self, kind: str, payload: dict, actor: str,
                idempotency_key: str | None = None, max_attempts: int | None = None) -> Job: ...

    def claim(self, actor: str, kinds: list[str] | None = None) -> Job | None: ...

    def complete(self, job_id: str, actor: str, claim_token: str) -> Job: ...

    def heartbeat(self, job_id: str, actor: str, claim_token: str) -> Job: ...

    def fail(self, job_id: str, error: str, actor: str, claim_token: str, retryable: bool = True) -> Job: ...

    def cancel(self, job_id: str, actor: str) -> Job: ...

    def requeue(self, job_id: str, actor: str) -> Job: ...

    def get_job(self, job_id: str) -> Job | None: ...

    def list_jobs(self, status: str | None = None) -> list[Job]: ...

    def run_once(self, handler: Callable[[Job], None], actor: str,
                 kinds: list[str] | None = None) -> Job | None: ...
