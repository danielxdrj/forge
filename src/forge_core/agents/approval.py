"""Política e registro de aprovação (ADR-011).

A concessão exige um Principal verificado com papel `approver`, nunca texto. Não é autoaprovação: o aprovador
não pode ter alterado a tarefa. A concessão vale só para a versão aprovada. `decide` continua sem liberar
agente privilegiado: a autenticação de aprovador não libera execução por si (ADR-011 e ADR-014).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..errors import ApprovalError, AuthenticationError, AuthorizationError
from ..auth.store import AuthStore
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
    """Concessão em `approval_grants` (ligada à identidade e à versão) e reserva atômica de uso único.

    `reserve` insere o grant_id em `grant_consumptions` (chave primária, namespace próprio de `approval_grants`). Duas reservas concorrentes da
    mesma concessão: só uma vence. A reserva confere, no momento do consumo, que a versão ainda é a aprovada
    e que o aprovador ainda tem o papel `approver`. Concessão revogada ou versão alterada não libera.
    """

    def __init__(self, repo: SqlRepository, clock: Callable[[], datetime] | None = None):
        self._repo = repo
        self._auth = AuthStore(repo)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._after_candidate_read: Callable[[], None] | None = None  # gancho de teste

    def _task_version(self, task_id: str, tx=None, lock: bool = False) -> int | None:
        sql = "SELECT version FROM tasks WHERE id = ?"
        if lock and self._repo.dialect != "sqlite":
            sql += " FOR UPDATE"
        rows = tx.execute(sql, (task_id,)).fetchall() if tx is not None else self._repo.fetch(sql, (task_id,))
        return rows[0][0] if rows else None

    def grant(self, task_id: str, approver, agent: str) -> None:
        if self._task_version(task_id) is None:
            raise ApprovalError("aprovação recusada: tarefa inexistente")
        try:
            principal = self._auth.require(approver, "approver")
        except AuthenticationError as exc:
            self._refuse("nao_autenticado", task_id, str(exc))
        except AuthorizationError as exc:
            self._refuse(getattr(approver, "identity_id", "nao_autenticado"), task_id, str(exc))
        refusal = None
        try:
            with self._auth.authorized(principal, "approver") as tx:
                version = self._task_version(task_id, tx, lock=True)
                authors = self._auth.editors_of(task_id, tx)
                if version is None:
                    refusal = "tarefa inexistente"
                elif any(not a.startswith(("gh:", "agente:", "sistema:")) for a in authors):
                    refusal = "untrusted_authorship"
                elif principal.identity_id in authors:
                    refusal = "self_approval"
                else:
                    tx.execute("INSERT INTO approval_grants (task_id, agent, task_version, identity_id, granted_at) "
                               "VALUES (?, ?, ?, ?, ?)",
                               (task_id, agent, version, principal.identity_id, self._clock().isoformat()))
                    tx.audit(principal.identity_id, "approval.granted", f"task:{task_id}",
                             f"ok: agent={agent} version={version}")
        except (AuthenticationError, AuthorizationError) as exc:
            self._refuse(principal.identity_id, task_id, str(exc))
        if refusal is not None:
            self._refuse(principal.identity_id, task_id, refusal)

    def _refuse(self, actor: str, task_id: str, reason: str) -> None:
        self._repo.record_audit(actor, "approval.granted", f"task:{task_id}", f"error: {reason}")
        raise ApprovalError(f"aprovação recusada: {reason}")

    _CANDIDATE = (
        "SELECT g.id FROM approval_grants g WHERE g.task_id = ? AND g.agent = ? AND g.task_version = ? "
        "AND NOT EXISTS (SELECT 1 FROM grant_consumptions c WHERE c.grant_id = g.id) "
        "AND EXISTS (SELECT 1 FROM role_grants rg WHERE rg.identity_id = g.identity_id AND rg.role = 'approver' "
        "AND NOT EXISTS (SELECT 1 FROM role_revocations rv WHERE rv.grant_id = rg.id)) ORDER BY g.id"
    )

    def available(self, task_id: str, agent: str) -> int:
        version = self._task_version(task_id)
        if version is None:
            return 0
        rows = self._repo.fetch(
            "SELECT COUNT(*) FROM (" + self._CANDIDATE + ") x", (task_id, agent, version))
        return rows[0][0]

    def reserve(self, task_id: str, agent: str, consumed_by: str) -> int | None:
        """Consome uma concessão disponível e devolve o grant_id, ou None se não houver.

        Versão, papel do aprovador e consumo são conferidos e gravados na MESMA transação, depois de
        serializada com revogações (`serialize_authorization`) e com o bloqueio da linha da tarefa.
        """
        for _ in range(_MAX_ATTEMPTS):
            try:
                with self._repo.transaction() as tx:
                    self._auth.serialize_authorization(tx)
                    version = self._task_version(task_id, tx, lock=True)
                    if version is None:
                        return None
                    rows = tx.execute(self._CANDIDATE + " LIMIT 1", (task_id, agent, version)).fetchall()
                    if not rows:
                        return None
                    grant_id = rows[0][0]
                    if self._after_candidate_read is not None:
                        self._after_candidate_read()
                    tx.execute(
                        "INSERT INTO grant_consumptions (grant_id, task_id, agent, consumed_by, consumed_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (grant_id, task_id, agent, consumed_by, self._clock().isoformat()))
                    tx.audit(consumed_by, "approval.consumed", f"task:{task_id}",
                             f"ok: agent={agent} grant={grant_id}")
                    return grant_id
            except Exception as exc:
                if type(exc).__name__ not in ("IntegrityError", "UniqueViolation"):
                    raise
        return None
