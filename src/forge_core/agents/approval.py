"""Política e registro de aprovação (ADR-011).

IMPORTANTE: a aprovação registra o ator informado e NÃO autentica quem aprova. Por isso, hoje, nenhuma
aprovação libera a execução de agente privilegiado: `decide` nunca devolve ALLOW para quem exige
aprovação. O registro e a reserva atômica existem para o contrato ficar certo quando houver
autenticação de aprovadores e uma nova ADR.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..errors import ApprovalError
from ..storage.sql import SqlRepository
from .spec import AgentSpec

ALLOW = "allow"
NEEDS_APPROVAL = "needs_approval"
DISABLED = "disabled"
PRIVILEGED_DISABLED_MESSAGE = "privileged agents disabled until approver authentication"

_MAX_ATTEMPTS = 5


def decide(spec: AgentSpec, approved: bool) -> str:
    """Só agentes exclusivamente `read` são liberados. Privilegiado sem aprovação pede aprovação; com
    aprovação continua DESLIGADO, porque não existe autenticação de aprovadores."""
    if not spec.requires_approval:
        return ALLOW
    if not approved:
        return NEEDS_APPROVAL
    return DISABLED


class ApprovalLedger:
    """Concessão (`approval.granted` no audit_log) e reserva atômica de uso único por concessão.

    Uma concessão = uma linha do audit_log (seu id é o grant_id). `reserve` insere o grant_id em
    `approval_consumptions` (chave primária): duas reservas concorrentes da mesma concessão, só uma
    vence. O consumo vale mesmo que a execução depois falhe; retry, replay ou novo job exigem nova
    aprovação.
    """

    def __init__(self, repo: SqlRepository, clock: Callable[[], datetime] | None = None):
        self._repo = repo
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._after_candidate_read: Callable[[], None] | None = None  # gancho de teste

    def grant(self, task_id: str, approver: str, agent: str) -> None:
        if not approver.startswith("pessoa:"):
            self._repo.record_audit(approver, "approval.granted", f"task:{task_id}", "error: aprovador não é pessoa")
            raise ApprovalError("aprovação exige um ator pessoa:*")
        self._repo.record_audit(approver, "approval.granted", f"task:{task_id}", f"ok: agent={agent}")

    _CANDIDATE = (
        "SELECT a.id FROM audit_log a WHERE a.action = 'approval.granted' AND a.target = ? AND a.result = ? "
        "AND substr(a.actor, 1, 7) = 'pessoa:' "
        "AND NOT EXISTS (SELECT 1 FROM approval_consumptions c WHERE c.grant_id = a.id) ORDER BY a.id"
    )

    def available(self, task_id: str, agent: str) -> int:
        rows = self._repo.fetch(self._CANDIDATE.replace("SELECT a.id", "SELECT COUNT(*)", 1).split(" ORDER BY")[0],
                                (f"task:{task_id}", f"ok: agent={agent}"))
        return rows[0][0]

    def reserve(self, task_id: str, agent: str, consumed_by: str) -> int | None:
        """Consome uma concessão disponível e devolve o grant_id, ou None se não houver."""
        target, result = f"task:{task_id}", f"ok: agent={agent}"
        for _ in range(_MAX_ATTEMPTS):
            try:
                with self._repo.transaction() as tx:
                    rows = tx.execute(self._CANDIDATE + " LIMIT 1", (target, result)).fetchall()
                    if not rows:
                        return None
                    grant_id = rows[0][0]
                    if self._after_candidate_read is not None:
                        self._after_candidate_read()
                    tx.execute(
                        "INSERT INTO approval_consumptions (grant_id, task_id, agent, consumed_by, consumed_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (grant_id, task_id, agent, consumed_by, self._clock().isoformat()))
                    tx.audit(consumed_by, "approval.consumed", target, f"ok: agent={agent} grant={grant_id}")
                    return grant_id
            except Exception as exc:
                if type(exc).__name__ not in ("IntegrityError", "UniqueViolation"):
                    raise
                # outra reserva levou esta concessão: tenta a próxima disponível
        return None
