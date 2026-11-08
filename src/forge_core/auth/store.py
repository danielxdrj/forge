"""Identidades, papéis e sessões humanas (FRG autenticação). Toda decisão de autoridade passa por aqui.

Regras:
- Identidade = id numérico do GitHub (`gh:<id>`). Login é só exibição (snapshot na sessão).
- Papéis (owner, editor, approver) são concedidos e revogados por linhas append-only. Revogação vale na
  próxima operação: não há cache de papel nem de sessão.
- Só existe um dono inicial, por bootstrap explícito (linha única em `bootstrap_owner`).
- Sessões e bootstrap só nascem de um token OAuth verificado pelo GitHub (`verify`). Não há entrada que
  aceite id ou login informados pelo chamador.
- `Principal` só é produzido por `resolve_session`, que confere o token no banco. Texto (`pessoa:*`) nunca
  concede autoridade.

Fronteira: quem controla o processo, o banco ou o sistema operacional pode contornar isto. A biblioteca não
é um cofre contra o próprio operador local.
"""
from __future__ import annotations

import hashlib
import secrets
from contextlib import contextmanager
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from collections.abc import Callable

from ..errors import AuthenticationError, AuthorizationError, ConfigError
from ..storage.sql import SqlRepository
from .github import GitHubIdentity

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


def identity_id_for(github_id: int) -> str:
    return f"gh:{github_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_integrity_error(exc: Exception) -> bool:
    return type(exc).__name__ in ("IntegrityError", "UniqueViolation")


class AuthStore:
    def __init__(self, repo: SqlRepository, verify: Callable[[str], "GitHubIdentity"] | None = None):
        self._repo = repo
        self._verify = verify

    # --- identidade e bootstrap ---

    def _upsert_identity(self, tx, github_id: int, login: str) -> str:
        iid = identity_id_for(github_id)
        tx.execute("INSERT INTO identities (id, github_id, login, created_at) "
                   "SELECT ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM identities WHERE github_id = ?)",
                   (iid, github_id, login, _now(), github_id))
        return iid

    def serialize_authorization(self, tx) -> None:
        """Serializa com revogações e consumos de autorização na mesma transação.

        SQLite: `BEGIN IMMEDIATE` já serializa escritores (no-op aqui). PostgreSQL: lock consultivo de
        transação, sem privilégio de tabela extra. Sem isso, uma revogação poderia cair entre a checagem e o INSERT.
        """
        if self._repo.dialect != "sqlite":
            tx.execute("SELECT pg_advisory_xact_lock(hashtext('forge:autorizacao'))")

    def has_owner(self) -> bool:
        return bool(self._repo.fetch("SELECT 1 FROM bootstrap_owner"))

    def _verified(self, access_token: str) -> tuple[int, str]:
        """Identidade vem SOMENTE do GitHub, a partir do token OAuth. Nunca de id ou login informados."""
        if self._verify is None:
            raise ConfigError("verificação de identidade não configurada")
        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationError("invalid_identity")
        ident = self._verify(access_token)
        return ident.github_id, ident.login

    def bootstrap_owner(self, access_token: str, expected_github_id: int) -> tuple[Principal, str]:
        """Primeiro dono. Exige o id GitHub esperado (âncora do operador) e confere a identidade verificada.

        Só funciona uma vez: a segunda chamada, ou a concorrente, é recusada pela linha singleton.
        A identidade é conferida antes de qualquer escrita.
        """
        if self.has_owner():
            raise AuthorizationError("bootstrap_already_done")
        github_id, login = self._verified(access_token)
        if github_id != expected_github_id:
            raise AuthenticationError("bootstrap_identity_mismatch")
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
        return self._open(github_id, login)

    # --- sessão ---

    def open_session(self, access_token: str) -> tuple[Principal, str]:
        """Sessão para a identidade verificada pelo GitHub. Devolve (Principal, token); no banco fica só o hash."""
        github_id, login = self._verified(access_token)
        return self._open(github_id, login)

    def _open(self, github_id: int, login: str) -> tuple[Principal, str]:
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

    @contextmanager
    def authorized(self, principal, role: str | None):
        """Seção crítica de escrita: serializa com revogações e confere sessão e papel DENTRO da transação.

        Linearização: uma revogação confirmada antes do lock desta seção vale (a escrita é recusada). Uma escrita
        que confirma antes do lock da revogação permanece, e a revogação vale só para operações seguintes.
        A checagem de fora da seção (`require`) é só para recusa rápida, nunca a autoridade.
        """
        if role is not None and role not in ROLES:
            raise AuthorizationError("role_unknown")
        denied: Exception | None = None
        with self._repo.transaction() as tx:
            self.serialize_authorization(tx)
            try:
                self._check_in_tx(tx, principal, role)
            except (AuthenticationError, AuthorizationError) as exc:
                denied = exc
            if denied is None:
                yield tx
        if denied is not None:
            who = principal.identity_id if isinstance(principal, Principal) else "nao_autenticado"
            self._repo.record_audit(who, "auth.denied", f"role:{role or 'sessao'}", f"error: {denied}")
            raise denied

    def _check_in_tx(self, tx, principal, role: str | None) -> None:
        if not isinstance(principal, Principal):
            raise AuthenticationError("principal_missing")
        rows = tx.execute(
            "SELECT 1 FROM sessions s WHERE s.id = ? AND s.identity_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM session_revocations r WHERE r.session_id = s.id)",
            (principal.session_id, principal.identity_id)).fetchall()
        if not rows:
            raise AuthenticationError("invalid_session")
        if role is not None and not self._has_role_in_tx(tx, principal.identity_id, role):
            raise AuthorizationError("forbidden")

    @staticmethod
    def _has_role_in_tx(tx, identity_id: str, role: str) -> bool:
        return bool(tx.execute(
            "SELECT 1 FROM role_grants g WHERE g.identity_id = ? AND g.role = ? "
            "AND NOT EXISTS (SELECT 1 FROM role_revocations v WHERE v.grant_id = g.id)",
            (identity_id, role)).fetchall())

    def revoke_session(self, principal: Principal) -> None:
        with self.authorized(principal, None) as tx:
            tx.execute("INSERT INTO session_revocations (session_id, revoked_at) VALUES (?, ?)",
                       (principal.session_id, _now()))
            tx.audit(principal.identity_id, "auth.session_revoke", f"session:{principal.session_id}", "ok")

    def transition_actor(self, actor) -> str:
        """Autor de uma transição de status: sempre uma pessoa autenticada com papel `editor` agora."""
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
        """Recusa rápida fora da seção crítica. A autoridade é conferida de novo dentro de `authorized`."""
        if role not in ROLES:
            raise AuthorizationError("role_unknown")
        self.require_session(principal)
        if not self.has_role(principal.identity_id, role):
            self._repo.record_audit(principal.identity_id, "auth.denied", f"role:{role}", "error: forbidden")
            raise AuthorizationError("forbidden")
        return principal

    def grant_role(self, owner, github_id: int, role: str) -> None:
        iid = identity_id_for(github_id)
        with self.authorized(owner, "owner") as tx:
            if role not in ROLES or role == "owner":
                raise AuthorizationError("role_unknown")
            if not tx.execute("SELECT 1 FROM identities WHERE id = ?", (iid,)).fetchall():
                raise AuthorizationError("identity_unknown")
            tx.execute("INSERT INTO role_grants (identity_id, role, granted_by, granted_at) VALUES (?, ?, ?, ?)",
                       (iid, role, owner.identity_id, _now()))
            tx.audit(owner.identity_id, "auth.grant", f"identity:{iid}", f"ok: role={role}")

    def revoke_role(self, owner, grant_id: int) -> None:
        with self.authorized(owner, "owner") as tx:
            rows = tx.execute("SELECT identity_id, role FROM role_grants WHERE id = ?", (grant_id,)).fetchall()
            if not rows:
                raise AuthorizationError("grant_unknown")
            iid, role = rows[0]
            if role == "owner" and self._active_owner_count(tx) <= 1:
                raise AuthorizationError("last_owner")
            if tx.execute("SELECT 1 FROM role_revocations WHERE grant_id = ?", (grant_id,)).fetchall():
                raise AuthorizationError("grant_already_revoked")
            tx.execute("INSERT INTO role_revocations (grant_id, revoked_by, revoked_at) VALUES (?, ?, ?)",
                       (grant_id, owner.identity_id, _now()))
            tx.audit(owner.identity_id, "auth.revoke", f"identity:{iid}", f"ok: role={role}")

    def _active_owner_count(self, tx=None) -> int:
        sql = ("SELECT COUNT(*) FROM role_grants g WHERE g.role = 'owner' "
               "AND NOT EXISTS (SELECT 1 FROM role_revocations v WHERE v.grant_id = g.id)")
        rows = tx.execute(sql).fetchall() if tx is not None else self._repo.fetch(sql)
        return rows[0][0]

    def editors_of(self, task_id: str, tx=None) -> set[str]:
        """Identidades que alteraram ou mudaram o status da tarefa, em qualquer versão."""
        sql = "SELECT actor FROM task_changes WHERE task_id = ? UNION SELECT actor FROM task_history WHERE task_id = ?"
        rows = (tx.execute(sql, (task_id, task_id)).fetchall() if tx is not None
                else self._repo.fetch(sql, (task_id, task_id)))
        return {r[0] for r in rows}

    def principal_for_dispatch(self, dispatch_id: str) -> Principal:
        """Reabre uma sessão em memória para o pedido de despacho, se o editor ainda tiver o papel.

        Não lê token OAuth nem bearer: o vínculo é a linha `dispatch_requests` gravada no enqueue.
        O token da sessão nova não sai daqui (só o hash no banco). Quem chama revoga ao terminar.
        """
        token = secrets.token_urlsafe(32)
        sid = uuid.uuid4().hex
        with self._repo.transaction() as tx:
            self.serialize_authorization(tx)
            rows = tx.execute(
                "SELECT identity_id FROM dispatch_requests WHERE id = ?", (dispatch_id,)).fetchall()
            if len(rows) != 1:
                raise AuthenticationError("invalid_session")
            iid = rows[0][0]
            if not self._has_role_in_tx(tx, iid, "editor"):
                raise AuthorizationError("forbidden")
            ident = tx.execute("SELECT github_id, login FROM identities WHERE id = ?", (iid,)).fetchall()
            if len(ident) != 1:
                raise AuthenticationError("invalid_session")
            github_id, login = ident[0]
            tx.execute("INSERT INTO sessions (id, identity_id, token_hash, login, created_at) VALUES (?, ?, ?, ?, ?)",
                       (sid, iid, _digest(token), login, _now()))
            tx.audit(iid, "auth.session_open", f"session:{sid}", "ok: dispatch")
        del token
        return Principal(iid, login, sid, _issued=_ISSUED)
