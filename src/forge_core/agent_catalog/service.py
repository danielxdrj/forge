"""Catálogo e governança de agentes (aba "Agentes"): cadastro, métricas e aprovação de escrita.

Tabelas `agents`/`agent_executions`/`agent_approvals` (migração 0019). Sem execução aqui:
é cadastro e monitoramento. Agente de escopo `company_system` que nasce com alguma permissão
de escrita cria um pedido em `agent_approvals` (status `pending`); aprovar não libera escrita
em FTP/banco/Portainer — esses recursos ficam sempre em "Sem acesso" (coerente com o guard
real de `connections/readonly.py`, item 3): a validação recusa a permissão antes de persistir.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..auth.store import AuthStore, Principal
from ..errors import AuthorizationError, ForgeError
from ..logging import redact
from ..storage.sql import SqlRepository

SCOPES = ("development", "company_system")
STATUSES = ("active", "paused", "error")
EXECUTION_STATUSES = ("ok", "error", "running")
APPROVAL_DECISIONS = ("approved", "rejected")
MAX_NAME = 120
MAX_DESCRIPTION = 2000
MAX_TRIGGER = 200
MAX_ENGINE = 60
MAX_PERMISSIONS = 40
MAX_PERMISSION_LEN = 80
EXECUTIONS_PAGE = 20

# Mesmos recursos travados de verdade em connections/readonly.py: escrita nunca é permitida,
# nem depois de aprovação (coerência com o item 3 — "Sem acesso" é sempre a resposta real).
WRITE_LOCKED_RESOURCES = frozenset({
    "ftp", "sftp", "database", "db", "sql", "postgres", "postgresql", "mysql", "portainer", "docker",
})


class AgentRuleError(ForgeError):
    """Validação ou estado do agente/aprovação. Código fixo; nunca inclui log bruto."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class AgentView:
    id: str
    name: str
    description: str
    scope: str
    status: str
    trigger: str
    engine: str
    permissions_read: tuple
    permissions_write: tuple
    permissions_denied: tuple
    created_at: str
    updated_at: str

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "status": self.status,
            "trigger": self.trigger,
            "engine": self.engine,
            "permissions": {
                "read": list(self.permissions_read),
                "write": list(self.permissions_write),
                "denied": list(self.permissions_denied),
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ExecutionView:
    id: str
    agent_id: str
    started_at: str
    finished_at: str | None
    status: str
    event: str
    duration_ms: int | None
    log: str

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "event": self.event,
            "duration_ms": self.duration_ms,
            "log": self.log,
        }


@dataclass(frozen=True)
class ApprovalView:
    id: str
    agent_id: str
    agent_name: str
    action: str
    details: str
    status: str
    requested_at: str
    decided_at: str | None
    decided_by: str | None

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action": self.action,
            "details": self.details,
            "status": self.status,
            "requested_at": self.requested_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(raw, max_len: int, code: str, *, allow_empty: bool = False) -> str:
    if raw is None:
        raw = ""
    if not isinstance(raw, str):
        raise AgentRuleError(code)
    text = raw.strip()
    if (not text and not allow_empty) or len(text) > max_len:
        raise AgentRuleError(code)
    return text


def _permissions(raw) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_PERMISSIONS:
        raise AgentRuleError("invalid_permissions")
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip().lower()
        if not text or len(text) > MAX_PERMISSION_LEN:
            raise AgentRuleError("invalid_permissions")
        if text not in out:
            out.append(text)
    return out


def _loads_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _agent_from_row(row) -> AgentView:
    (ident, name, description, scope, status, trigger, engine,
     read_json, write_json, denied_json, created_at, updated_at) = row
    return AgentView(
        id=ident, name=name, description=description, scope=scope, status=status,
        trigger=trigger, engine=engine,
        permissions_read=tuple(_loads_list(read_json)),
        permissions_write=tuple(_loads_list(write_json)),
        permissions_denied=tuple(_loads_list(denied_json)),
        created_at=created_at, updated_at=updated_at,
    )


def _execution_from_row(row) -> ExecutionView:
    ident, agent_id, started_at, finished_at, status, event, duration_ms, log = row
    return ExecutionView(
        id=ident, agent_id=agent_id, started_at=started_at, finished_at=finished_at,
        status=status, event=event, duration_ms=duration_ms, log=log,
    )


def _approval_from_row(row) -> ApprovalView:
    ident, agent_id, agent_name, action, details, status, requested_at, decided_at, decided_by = row
    return ApprovalView(
        id=ident, agent_id=agent_id, agent_name=agent_name, action=action, details=details,
        status=status, requested_at=requested_at, decided_at=decided_at, decided_by=decided_by,
    )


AGENT_COLUMNS = (
    "id, name, description, scope, status, trigger, engine, "
    "permissions_read, permissions_write, permissions_denied, created_at, updated_at"
)


class AgentCatalogService:
    def __init__(self, repo: SqlRepository, store: AuthStore):
        self._repo = repo
        self._store = store

    # --- leitura ---

    def list_agents(self, principal: Principal) -> dict:
        self._require_reader(principal)
        rows = self._repo.fetch(
            f"SELECT {AGENT_COLUMNS} FROM agents ORDER BY lower(name), id",
        )
        agents = [_agent_from_row(r) for r in rows]
        stats = self._agent_stats([a.id for a in agents])
        agent_views = []
        for a in agents:
            view = a.as_json()
            view.update(stats.get(a.id) or {"last_execution_at": None, "success_rate": None})
            agent_views.append(view)
        return {"agents": agent_views, "metrics": self._metrics(agents)}

    def _agent_stats(self, agent_ids: list[str]) -> dict[str, dict]:
        """Última execução e taxa de sucesso (até as 20 mais recentes) por agente."""
        if not agent_ids:
            return {}
        placeholders = ",".join("?" for _ in agent_ids)
        rows = self._repo.fetch(
            f"SELECT agent_id, started_at, status FROM agent_executions "
            f"WHERE agent_id IN ({placeholders}) ORDER BY started_at DESC",
            tuple(agent_ids),
        )
        by_agent: dict[str, list[tuple[str, str]]] = {}
        for agent_id, started_at, status in rows:
            by_agent.setdefault(agent_id, []).append((started_at, status))
        out: dict[str, dict] = {}
        for agent_id, items in by_agent.items():
            window = items[:20]
            ok = sum(1 for _, status in window if status == "ok")
            out[agent_id] = {
                "last_execution_at": items[0][0],
                "success_rate": round(100 * ok / len(window)) if window else None,
            }
        return out

    def get_agent(self, principal: Principal, agent_id: str) -> dict:
        self._require_reader(principal)
        agent = self._load(agent_id)
        if agent is None:
            raise AgentRuleError("not_found")
        rows = self._repo.fetch(
            "SELECT id, agent_id, started_at, finished_at, status, event, duration_ms, log "
            "FROM agent_executions WHERE agent_id = ? ORDER BY started_at DESC, id DESC LIMIT ?",
            (agent_id, EXECUTIONS_PAGE),
        )
        executions = [_execution_from_row(r) for r in rows]
        return {"agent": agent.as_json(), "executions": [e.as_json() for e in executions]}

    def list_approvals(self, principal: Principal) -> list[ApprovalView]:
        self._require_reader(principal)
        rows = self._repo.fetch(
            "SELECT ap.id, ap.agent_id, a.name, ap.action, ap.details, ap.status, "
            "ap.requested_at, ap.decided_at, ap.decided_by "
            "FROM agent_approvals ap JOIN agents a ON a.id = ap.agent_id "
            "ORDER BY ap.requested_at DESC, ap.id DESC",
        )
        return [_approval_from_row(r) for r in rows]

    # --- escrita ---

    def create(self, principal: Principal, payload: dict) -> AgentView:
        self._store.require(principal, "owner")
        if not isinstance(payload, dict):
            raise AgentRuleError("invalid_json")
        name = _text(payload.get("name"), MAX_NAME, "invalid_name")
        description = _text(payload.get("description"), MAX_DESCRIPTION, "invalid_description", allow_empty=True)
        scope = str(payload.get("scope") or "").strip()
        if scope not in SCOPES:
            raise AgentRuleError("invalid_scope")
        status = str(payload.get("status") or "active").strip()
        if status not in STATUSES:
            raise AgentRuleError("invalid_status")
        trigger = _text(payload.get("trigger"), MAX_TRIGGER, "invalid_trigger", allow_empty=True)
        engine = _text(payload.get("engine"), MAX_ENGINE, "invalid_engine", allow_empty=True)
        read = _permissions(payload.get("permissions_read"))
        write = _permissions(payload.get("permissions_write"))
        denied = _permissions(payload.get("permissions_denied"))
        _assert_write_allowed(write)
        agent_id = str(uuid.uuid4())
        ts = _now()
        needs_approval = scope == "company_system" and bool(write)
        try:
            with self._repo.transaction() as tx:
                tx.execute(
                    f"INSERT INTO agents ({AGENT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        agent_id, name, description, scope, status, trigger, engine,
                        json.dumps(read), json.dumps(write), json.dumps(denied), ts, ts,
                    ),
                )
                if needs_approval:
                    tx.execute(
                        "INSERT INTO agent_approvals (id, agent_id, action, details, status, requested_at) "
                        "VALUES (?, ?, 'write_access', ?, 'pending', ?)",
                        (str(uuid.uuid4()), agent_id, json.dumps(write), ts),
                    )
                tx.audit(
                    principal.identity_id, "agent.create", f"agent:{agent_id}",
                    f"ok: scope={scope} status={status} approval_pending={needs_approval}",
                )
        except Exception as exc:
            if type(exc).__name__ in ("IntegrityError", "UniqueViolation"):
                raise AgentRuleError("name_taken") from exc
            raise
        return self._load(agent_id)

    def update(self, principal: Principal, agent_id: str, payload: dict) -> AgentView:
        self._store.require(principal, "owner")
        if not isinstance(payload, dict):
            raise AgentRuleError("invalid_json")
        current = self._load(agent_id)
        if current is None:
            raise AgentRuleError("not_found")
        status = str(payload.get("status") or current.status).strip()
        if status not in STATUSES:
            raise AgentRuleError("invalid_status")
        ts = _now()
        with self._repo.transaction() as tx:
            tx.execute("UPDATE agents SET status = ?, updated_at = ? WHERE id = ?", (status, ts, agent_id))
            tx.audit(principal.identity_id, "agent.update", f"agent:{agent_id}", f"ok: status={status}")
        return self._load(agent_id)

    def decide_approval(self, principal: Principal, approval_id: str, decision: str) -> ApprovalView:
        self._store.require(principal, "owner")
        if decision not in APPROVAL_DECISIONS:
            raise AgentRuleError("invalid_decision")
        rows = self._repo.fetch("SELECT status FROM agent_approvals WHERE id = ?", (approval_id,))
        if not rows:
            raise AgentRuleError("not_found")
        if rows[0][0] != "pending":
            raise AgentRuleError("already_decided")
        ts = _now()
        with self._repo.transaction() as tx:
            tx.execute(
                "UPDATE agent_approvals SET status = ?, decided_at = ?, decided_by = ? "
                "WHERE id = ? AND status = 'pending'",
                (decision, ts, principal.identity_id, approval_id),
            )
            tx.audit(
                principal.identity_id, "agent.approval_decide", f"approval:{approval_id}", f"ok: {decision}",
            )
        return self._load_approval(approval_id)

    def record_execution(
        self, agent_id: str, *, status: str, event: str = "", log: str = "",
        duration_ms: int | None = None, started_at: str | None = None, finished_at: str | None = None,
    ) -> ExecutionView:
        """Registro de execução (chamado por quem orquestra de fato; aqui só persistimos)."""
        if status not in EXECUTION_STATUSES:
            raise AgentRuleError("invalid_status")
        if self._load(agent_id) is None:
            raise AgentRuleError("not_found")
        exec_id = str(uuid.uuid4())
        ts = started_at or _now()
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO agent_executions (id, agent_id, started_at, finished_at, status, event, "
                "duration_ms, log) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (exec_id, agent_id, ts, finished_at, status, event, duration_ms, redact(log)),
            )
            tx.audit("sistema:agent_catalog", "agent.execution", f"agent:{agent_id}", f"ok: status={status}")
        rows = self._repo.fetch(
            "SELECT id, agent_id, started_at, finished_at, status, event, duration_ms, log "
            "FROM agent_executions WHERE id = ?",
            (exec_id,),
        )
        return _execution_from_row(rows[0])

    # --- internos ---

    def _require_reader(self, principal: Principal) -> None:
        self._store.require_session(principal)
        ident = principal.identity_id
        if self._store.has_role(ident, "editor") or self._store.has_role(ident, "owner"):
            return
        self._repo.record_audit(ident, "auth.denied", "role:agent_reader", "error: forbidden")
        raise AuthorizationError("forbidden")

    def _load(self, agent_id: str) -> AgentView | None:
        rows = self._repo.fetch(f"SELECT {AGENT_COLUMNS} FROM agents WHERE id = ?", (agent_id,))
        if not rows:
            return None
        return _agent_from_row(rows[0])

    def _load_approval(self, approval_id: str) -> ApprovalView | None:
        rows = self._repo.fetch(
            "SELECT ap.id, ap.agent_id, a.name, ap.action, ap.details, ap.status, "
            "ap.requested_at, ap.decided_at, ap.decided_by "
            "FROM agent_approvals ap JOIN agents a ON a.id = ap.agent_id WHERE ap.id = ?",
            (approval_id,),
        )
        if not rows:
            return None
        return _approval_from_row(rows[0])

    def _metrics(self, agents: list[AgentView]) -> dict:
        total = len(agents)
        active = sum(1 for a in agents if a.status == "active")
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        since_24h = (now - timedelta(hours=24)).isoformat()
        exec_today_rows = self._repo.fetch(
            "SELECT COUNT(*) FROM agent_executions WHERE started_at >= ?", (today_start,),
        )
        errors_rows = self._repo.fetch(
            "SELECT COUNT(*) FROM agent_executions WHERE status = 'error' AND started_at >= ?",
            (since_24h,),
        )
        pending_rows = self._repo.fetch(
            "SELECT COUNT(*) FROM agent_approvals WHERE status = 'pending'",
        )
        return {
            "active": active,
            "total": total,
            "executions_today": exec_today_rows[0][0] if exec_today_rows else 0,
            "errors_24h": errors_rows[0][0] if errors_rows else 0,
            "pending_approvals": pending_rows[0][0] if pending_rows else 0,
        }


def _assert_write_allowed(write: list[str]) -> None:
    locked = [r for r in write if r in WRITE_LOCKED_RESOURCES]
    if locked:
        raise AgentRuleError("write_denied_resource", ",".join(locked))
