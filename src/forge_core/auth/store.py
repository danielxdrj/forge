"""Identidades, papéis e sessões humanas (FRG autenticação). Toda decisão de autoridade passa por aqui.

Regras:
- Identidade = id numérico do GitHub (`gh:<id>`). Login é só exibição (snapshot na sessão).
- Papéis (owner, editor, approver) são concedidos e revogados por linhas append-only. Revogação vale na
  próxima operação: não há cache de papel nem de sessão.
- Só existe um dono inicial, por bootstrap explícito (linha única em `bootstrap_owner`).
- `Principal` só é produzido por `resolve_session`, que confere o token no banco. Texto (`pessoa:*`) nunca
  concede autoridade.

Fronteira: quem controla o processo, o banco ou o sistema operacional pode contornar isto. A biblioteca não
é um cofre contra o próprio operador local.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..errors import AuthenticationError, AuthorizationError
from ..storage.sql import SqlRepository

ROLES = ("owner", "editor", "approver")
_ISSUED = object()


@dataclass(frozen=True)
class Principal:
    """Pessoa autenticada. Só `AuthStore.resolve_session` cria uma instância válida."""

    identity_id: str
    login: str
    session_id: str
    _issued: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issued is not _ISSUED:
            raise AuthenticationError("principal_forged")


@dataclass(frozen=True)
class SystemActor:
    """Atribuição de processo do Core (ex.: orquestrador). Não é pessoa: não aprova nem edita como humano.

    Só serve para as transições de status que o próprio sistema executa (`TaskService.change_status`).
    Texto nunca vale como sistema. Quem controla o processo pode instanciar isto: fronteira documentada (ADR-014).
    """

    name: str


ORCHESTRATOR_SYSTEM = SystemActor("orchestrator")


def identity_id_for(github_id: int) -> str:
    return f"gh:{github_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_integrity_error(exc: Exception) -> bool:
    return type(exc).__name__ in ("IntegrityError", "UniqueViolation")


class AuthStore:
    def __init__(self, repo: SqlRepository):
        self._repo = repo

    # --- identidade e bootstrap ---

    def _upsert_identity(self, tx, github_id: int, login: str) -> str:
        iid = identity_id_for(github_id)
        tx.execute("INSERT INTO identities (id, github_id, login, created_at) "
                   "SELECT ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM identities WHERE github_id = ?)",
                   (iid, github_id, login, _now(), github_id))
        return iid

    def bootstrap_owner(self, github_id: int, login: str) -> tuple[Principal, str]:
        """Primeiro dono da instalação. Só funciona uma vez; a segunda chamada (ou a concorrente) é recusada."""
        try:
            with self._repo.transaction() as tx:
                iid = self._upsert_identity(tx, github_id, login)
                tx.execute("INSERT INTO bootstrap_owner (singleton, identity_id, at) VALUES ('owner', ?, ?)",
                           (iid, _now()))
                tx.execute("INSERT INTO role_grants (identity_id, role, granted_by, granted_at) "
                           "VALUES (?, 'owner', 'bootstrap', ?)", (iid, _now()))
                tx.audit(iid, "auth.bootstrap", f"identity:{iid}", "ok")
        except Exception as exc:
            if _is_integrity_error(exc):
                self._repo.record_audit("sistema:auth", "auth.bootstrap", "identity:new", "error: ja_inicializado")
                raise AuthorizationError("bootstrap_already_done") from None
            raise
        return self.open_session(github_id, login)

    # --- sessão ---

    def open_session(self, github_id: int, login: str) -> tuple[Principal, str]:
        """Cria sessão. Devolve (Principal, token). O token é mostrado uma vez; no banco fica só o hash."""
        token = secrets.token_urlsafe(32)
        sid = uuid.uuid4().hex
        with self._repo.transaction() as tx:
            iid = self._upsert_identity(tx, github_id, login)
            tx.execute("INSERT INTO sessions (id, identity_id, token_hash, login, created_at) VALUES (?, ?, ?, ?, ?)",
                       (sid, iid, _digest(token), login, _now()))
            tx.audit(iid, "auth.session_open", f"session:{sid}", "ok")
        return Principal(iid, login, sid, _issued=_ISSUED), token

    def resolve_session(self, token: str) -> Principal:
        """Confere o token no banco a cada chamada. Falha genérica: nunca ecoa o token."""
        if not isinstance(token, str) or not token:
            raise AuthenticationError("invalid_session")
        rows = self._repo.fetch(
            "SELECT s.id, s.identity_id, s.login FROM sessions s WHERE s.token_hash = ? "
            "AND NOT EXISTS (SELECT 1 FROM session_revocations r WHERE r.session_id = s.id)",
            (_digest(token),))
        if len(rows) != 1:
            raise AuthenticationError("invalid_session")
        sid, iid, login = rows[0]
        return Principal(iid, login, sid, _issued=_ISSUED)

    def revoke_session(self, principal: Principal) -> None:
        self.require_session(principal)
        with self._repo.transaction() as tx:
            tx.execute("INSERT INTO session_revocations (session_id, revoked_at) VALUES (?, ?)",
                       (principal.session_id, _now()))
            tx.audit(principal.identity_id, "auth.session_revoke", f"session:{principal.session_id}", "ok")

    def transition_actor(self, actor) -> str:
        """Autor de uma transição de status: o orquestrador (SystemActor) ou uma pessoa com papel `editor`."""
        if isinstance(actor, SystemActor) and actor == ORCHESTRATOR_SYSTEM:
            return f"sistema:{actor.name}"
        return self.require(actor, "editor").identity_id

    def human_id(self, principal, role: str) -> str:
        """Identidade verificada para gravar como autor. Qualquer coisa que não seja Principal é recusada."""
        return self.require(principal, role).identity_id

    def require_session(self, principal: Principal) -> None:
        if not isinstance(principal, Principal):
            raise AuthenticationError("principal_missing")
        rows = self._repo.fetch(
            "SELECT 1 FROM sessions s WHERE s.id = ? AND s.identity_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM session_revocations r WHERE r.session_id = s.id)",
            (principal.session_id, principal.identity_id))
        if not rows:
            raise AuthenticationError("invalid_session")

    # --- papéis ---

    def has_role(self, identity_id: str, role: str) -> bool:
        rows = self._repo.fetch(
            "SELECT 1 FROM role_grants g WHERE g.identity_id = ? AND g.role = ? "
            "AND NOT EXISTS (SELECT 1 FROM role_revocations v WHERE v.grant_id = g.id)",
            (identity_id, role))
        return bool(rows)

    def require(self, principal, role: str) -> Principal:
        """Verificação por operação: sessão ativa E papel ativo agora. Negativa é auditada, sem segredos."""
        if role not in ROLES:
            raise AuthorizationError("role_unknown")
        self.require_session(principal)
        if not self.has_role(principal.identity_id, role):
            self._repo.record_audit(principal.identity_id, "auth.denied", f"role:{role}", "error: forbidden")
            raise AuthorizationError("forbidden")
        return principal

    def grant_role(self, owner, github_id: int, role: str) -> None:
        self.require(owner, "owner")
        if role not in ROLES or role == "owner":
            raise AuthorizationError("role_unknown")
        iid = identity_id_for(github_id)
        if not self._identity_exists(iid):
            raise AuthorizationError("identity_unknown")
        with self._repo.transaction() as tx:
            tx.execute("INSERT INTO role_grants (identity_id, role, granted_by, granted_at) VALUES (?, ?, ?, ?)",
                       (iid, role, owner.identity_id, _now()))
            tx.audit(owner.identity_id, "auth.grant", f"identity:{iid}", f"ok: role={role}")

    def revoke_role(self, owner, grant_id: int) -> None:
        self.require(owner, "owner")
        rows = self._repo.fetch("SELECT identity_id, role FROM role_grants WHERE id = ?", (grant_id,))
        if not rows:
            raise AuthorizationError("grant_unknown")
        iid, role = rows[0]
        if role == "owner" and self._active_owner_count() <= 1:
            raise AuthorizationError("last_owner")
        try:
            with self._repo.transaction() as tx:
                tx.execute("INSERT INTO role_revocations (grant_id, revoked_by, revoked_at) VALUES (?, ?, ?)",
                           (grant_id, owner.identity_id, _now()))
                tx.audit(owner.identity_id, "auth.revoke", f"identity:{iid}", f"ok: role={role}")
        except Exception as exc:
            if _is_integrity_error(exc):
                raise AuthorizationError("grant_already_revoked") from None
            raise

    def _identity_exists(self, iid: str) -> bool:
        return bool(self._repo.fetch("SELECT 1 FROM identities WHERE id = ?", (iid,)))

    def _active_owner_count(self) -> int:
        rows = self._repo.fetch(
            "SELECT COUNT(*) FROM role_grants g WHERE g.role = 'owner' "
            "AND NOT EXISTS (SELECT 1 FROM role_revocations v WHERE v.grant_id = g.id)")
        return rows[0][0]

    def editors_of(self, task_id: str) -> set[str]:
        """Identidades que alteraram ou mudaram o status da tarefa, em qualquer versão."""
        rows = self._repo.fetch(
            "SELECT actor FROM task_changes WHERE task_id = ? UNION SELECT actor FROM task_history WHERE task_id = ?",
            (task_id, task_id))
        return {r[0] for r in rows}
