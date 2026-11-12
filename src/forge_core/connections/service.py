"""Casos de uso de conexão: CRUD, ordem dos hosts e teste. O segredo só existe cifrado no banco."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..auth.store import AuthStore, Principal
from ..errors import AuthorizationError, ForgeError
from ..logging import redact
from ..storage.sql import SqlRepository
from .probes import CONNECTION_TYPES, ConnectionProbes, ProbeError
from .vault import ConnectionsVault, VaultDisabled

_HOST = re.compile(r"^[A-Za-z0-9._:-]{1,253}$")
_PROBE_HINTS = {
    "timeout": "tempo esgotado",
    "refused": "conexão recusada",
    "unreachable": "host inalcançável",
    "auth_failed": "autenticação recusada",
    "auth_unsupported": "método de autenticação não suportado",
    "protocol": "resposta de protocolo inesperada",
    "type_unsupported": "tipo não suportado",
    "secret_missing": "segredo não cadastrado",
}


class ConnectionRuleError(ForgeError):
    """Validação ou estado da conexão. Código fixo; sem segredo."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class HostView:
    id: str
    label: str
    host: str
    order: int


@dataclass(frozen=True)
class ConnectionView:
    id: str
    name: str
    type: str
    user: str
    port: int
    database: str | None
    path: str | None
    secret_set: bool
    preferred_host_id: str | None
    hosts: tuple[HostView, ...]
    created_at: str
    updated_at: str

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "user": self.user,
            "port": self.port,
            "database": self.database,
            "path": self.path,
            "secret_set": self.secret_set,
            "preferred_host_id": self.preferred_host_id,
            "hosts": [
                {"id": h.id, "label": h.label, "host": h.host, "order": h.order} for h in self.hosts
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_reader(store: AuthStore, principal: Principal) -> Principal:
    store.require_session(principal)
    if store.has_role(principal.identity_id, "editor") or store.has_role(principal.identity_id, "owner"):
        return principal
    store._repo.record_audit(principal.identity_id, "auth.denied", "role:connection_reader", "error: forbidden")
    raise AuthorizationError("forbidden")


class ConnectionService:
    def __init__(
        self,
        repo: SqlRepository,
        store: AuthStore,
        vault: ConnectionsVault,
        probes: ConnectionProbes | None = None,
    ):
        self._repo = repo
        self._store = store
        self._vault = vault
        self._probes = probes or ConnectionProbes()

    def status(self) -> dict:
        if not self._vault.enabled:
            return {
                "enabled": False,
                "error": self._vault.reason,
                "message": "Área Conexões desligada: chave de cifração ausente ou inválida. "
                "Gere uma chave Fernet e entregue-a em /run/secrets/forge_connections_key "
                "(FORGE_CONNECTIONS_KEY no compose; o entrypoint grava o arquivo e remove a variável).",
            }
        return {"enabled": True}

    def _need_vault(self) -> None:
        if not self._vault.enabled:
            raise ConnectionRuleError(self._vault.reason)

    def list_connections(self, principal: Principal) -> list[ConnectionView]:
        _require_reader(self._store, principal)
        self._need_vault()
        rows = self._repo.fetch(
            "SELECT id FROM connections ORDER BY name COLLATE NOCASE, id"
            if self._repo.dialect == "sqlite"
            else "SELECT id FROM connections ORDER BY lower(name), id"
        )
        return [self._load(row[0]) for row in rows]

    def get_connection(self, principal: Principal, connection_id: str) -> ConnectionView:
        _require_reader(self._store, principal)
        self._need_vault()
        view = self._load(connection_id)
        if view is None:
            raise ConnectionRuleError("not_found")
        return view

    def create(self, principal: Principal, data: dict, secret: str | None) -> ConnectionView:
        self._store.require(principal, "owner")
        self._need_vault()
        fields = _validated(data)
        cid = uuid.uuid4().hex
        hosts = _host_rows(cid, fields["hosts"])
        preferred = _preferred_id(hosts, fields.get("preferred_index"))
        ciphertext = None
        if secret:
            ciphertext = self._encrypt(secret)
        ts = _now()
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO connections (id, name, type, username, port, database_name, remote_path, "
                "secret_ciphertext, preferred_host_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cid, fields["name"], fields["type"], fields["user"], fields["port"],
                    fields["database"], fields["path"], ciphertext, preferred, ts, ts,
                ),
            )
            for host in hosts:
                tx.execute(
                    "INSERT INTO connection_hosts (id, connection_id, label, hostname, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (host.id, cid, host.label, host.host, host.order, ts),
                )
            tx.audit(
                principal.identity_id, "connection.create", f"connection:{cid}",
                f"ok: type={fields['type']} hosts={len(hosts)} secret_set={bool(ciphertext)}",
            )
        return self._load(cid)

    def update(self, principal: Principal, connection_id: str, data: dict, secret: str | None) -> ConnectionView:
        self._store.require(principal, "owner")
        self._need_vault()
        current = self._load(connection_id)
        if current is None:
            raise ConnectionRuleError("not_found")
        fields = _validated(data)
        hosts = _host_rows(connection_id, fields["hosts"])
        preferred = _preferred_id(hosts, fields.get("preferred_index"))
        ciphertext = current.secret_set
        new_cipher = None
        if secret:
            new_cipher = self._encrypt(secret)
        ts = _now()
        with self._repo.transaction() as tx:
            if new_cipher is not None:
                tx.execute(
                    "UPDATE connections SET name=?, type=?, username=?, port=?, database_name=?, remote_path=?, "
                    "secret_ciphertext=?, preferred_host_id=?, updated_at=? WHERE id=?",
                    (
                        fields["name"], fields["type"], fields["user"], fields["port"],
                        fields["database"], fields["path"], new_cipher, preferred, ts, connection_id,
                    ),
                )
            else:
                tx.execute(
                    "UPDATE connections SET name=?, type=?, username=?, port=?, database_name=?, remote_path=?, "
                    "preferred_host_id=?, updated_at=? WHERE id=?",
                    (
                        fields["name"], fields["type"], fields["user"], fields["port"],
                        fields["database"], fields["path"], preferred, ts, connection_id,
                    ),
                )
            tx.execute("DELETE FROM connection_hosts WHERE connection_id=?", (connection_id,))
            for host in hosts:
                tx.execute(
                    "INSERT INTO connection_hosts (id, connection_id, label, hostname, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (host.id, connection_id, host.label, host.host, host.order, ts),
                )
            tx.audit(
                principal.identity_id, "connection.update", f"connection:{connection_id}",
                f"ok: type={fields['type']} hosts={len(hosts)} secret_replaced={bool(new_cipher)} secret_set={bool(new_cipher or ciphertext)}",
            )
        return self._load(connection_id)

    def delete(self, principal: Principal, connection_id: str) -> None:
        self._store.require(principal, "owner")
        self._need_vault()
        if self._load(connection_id) is None:
            raise ConnectionRuleError("not_found")
        with self._repo.transaction() as tx:
            tx.execute("DELETE FROM connection_hosts WHERE connection_id=?", (connection_id,))
            tx.execute("DELETE FROM connections WHERE id=?", (connection_id,))
            tx.audit(principal.identity_id, "connection.delete", f"connection:{connection_id}", "ok")

    def test(self, principal: Principal, connection_id: str, preferred_host_id: str | None = None) -> dict:
        _require_reader(self._store, principal)
        self._need_vault()
        view = self._load(connection_id)
        if view is None:
            raise ConnectionRuleError("not_found")
        try:
            secret = self._secret_of(view)
        except ProbeError as exc:
            self._repo.record_audit(
                principal.identity_id, "connection.test", f"connection:{connection_id}",
                f"error: {exc.code}",
            )
            hint = _PROBE_HINTS.get(exc.code, exc.code)
            return {
                "ok": False, "host_id": None, "label": None, "host": None,
                "message": hint, "attempts": [],
            }
        ordered = _hosts_for_test(view, preferred_host_id)
        attempts = []
        winner = None
        for host in ordered:
            try:
                self._probes.test_one(
                    view.type, host.host, view.port, view.user, secret,
                    view.database, view.path,
                )
            except ProbeError as exc:
                attempts.append({
                    "host_id": host.id, "label": host.label, "host": host.host,
                    "ok": False, "error": exc.code, "message": _PROBE_HINTS.get(exc.code, exc.code),
                })
                continue
            attempts.append({
                "host_id": host.id, "label": host.label, "host": host.host,
                "ok": True, "error": None, "message": "ok",
            })
            winner = host
            break
        ok = winner is not None
        if ok:
            result = f"ok: host={winner.label}"
            message = f"Conectou em {winner.label} ({winner.host})."
        else:
            result = "error: " + ",".join(a["error"] for a in attempts)
            message = "Nenhum host respondeu. " + " ".join(
                f"{a['label']} ({a['host']}): {a['message']}." for a in attempts
            )
        self._repo.record_audit(
            principal.identity_id, "connection.test", f"connection:{connection_id}", redact(result),
        )
        return {
            "ok": ok,
            "host_id": winner.id if winner else None,
            "label": winner.label if winner else None,
            "host": winner.host if winner else None,
            "message": message,
            "attempts": attempts,
        }

    def _encrypt(self, secret: str) -> str:
        try:
            return self._vault.encrypt(secret)
        except VaultDisabled as exc:
            raise ConnectionRuleError(exc.reason) from exc

    def _secret_of(self, view: ConnectionView) -> str:
        rows = self._repo.fetch("SELECT secret_ciphertext FROM connections WHERE id=?", (view.id,))
        if not rows or not rows[0][0]:
            raise ProbeError("secret_missing")
        try:
            return self._vault.decrypt(rows[0][0])
        except VaultDisabled as exc:
            raise ConnectionRuleError(exc.reason) from exc

    def _load(self, connection_id: str) -> ConnectionView | None:
        rows = self._repo.fetch(
            "SELECT id, name, type, username, port, database_name, remote_path, secret_ciphertext, "
            "preferred_host_id, created_at, updated_at FROM connections WHERE id=?",
            (connection_id,),
        )
        if not rows:
            return None
        r = rows[0]
        hosts = self._repo.fetch(
            "SELECT id, label, hostname, sort_order FROM connection_hosts "
            "WHERE connection_id=? ORDER BY sort_order, id",
            (connection_id,),
        )
        return ConnectionView(
            id=r[0], name=r[1], type=r[2], user=r[3], port=int(r[4]),
            database=r[5], path=r[6], secret_set=bool(r[7]), preferred_host_id=r[8],
            hosts=tuple(HostView(h[0], h[1], h[2], int(h[3])) for h in hosts),
            created_at=r[9], updated_at=r[10],
        )


def _validated(data: dict) -> dict:
    name = str(data.get("name") or "").strip()
    conn_type = str(data.get("type") or "").strip().lower()
    user = str(data.get("user") or "").strip()
    if not name or len(name) > 200:
        raise ConnectionRuleError("invalid_name")
    if conn_type not in CONNECTION_TYPES:
        raise ConnectionRuleError("invalid_type")
    if not user or len(user) > 128:
        raise ConnectionRuleError("invalid_user")
    try:
        port = int(data.get("port"))
    except (TypeError, ValueError) as exc:
        raise ConnectionRuleError("invalid_port") from exc
    if port < 1 or port > 65535:
        raise ConnectionRuleError("invalid_port")
    database = _optional_text(data.get("database"), "invalid_database")
    path = _optional_text(data.get("path"), "invalid_path")
    if conn_type not in ("mysql", "postgres"):
        database = None
    if conn_type not in ("ftp", "sftp"):
        path = None
    hosts_in = data.get("hosts") or []
    if not isinstance(hosts_in, list) or not hosts_in or len(hosts_in) > 32:
        raise ConnectionRuleError("invalid_hosts")
    hosts = []
    for item in hosts_in:
        if not isinstance(item, dict):
            raise ConnectionRuleError("invalid_hosts")
        label = str(item.get("label") or "").strip()
        host = str(item.get("host") or "").strip()
        if not label or len(label) > 80:
            raise ConnectionRuleError("invalid_host_label")
        if not _HOST.fullmatch(host) or "@" in host or "/" in host:
            raise ConnectionRuleError("invalid_host")
        try:
            order = int(item.get("order", 0))
        except (TypeError, ValueError) as exc:
            raise ConnectionRuleError("invalid_host_order") from exc
        hosts.append({"label": label, "host": host, "order": order})
    preferred_index = data.get("preferred_index")
    if preferred_index is not None:
        try:
            preferred_index = int(preferred_index)
        except (TypeError, ValueError) as exc:
            raise ConnectionRuleError("invalid_preferred") from exc
        if preferred_index < 0 or preferred_index >= len(hosts):
            raise ConnectionRuleError("invalid_preferred")
    return {
        "name": name, "type": conn_type, "user": user, "port": port,
        "database": database, "path": path, "hosts": hosts, "preferred_index": preferred_index,
    }


def _optional_text(value, code: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > 1024:
        raise ConnectionRuleError(code)
    return text


def _host_rows(connection_id: str, hosts: list[dict]) -> list[HostView]:
    # connection_id reserved for callers that want stable ids; ids are fresh on each save.
    del connection_id
    return [
        HostView(id=uuid.uuid4().hex, label=h["label"], host=h["host"], order=int(h["order"]))
        for h in hosts
    ]


def _preferred_id(hosts: list[HostView], preferred_index: int | None) -> str:
    if not hosts:
        raise ConnectionRuleError("invalid_hosts")
    if preferred_index is None:
        return sorted(hosts, key=lambda h: (h.order, h.id))[0].id
    return hosts[preferred_index].id


def _hosts_for_test(view: ConnectionView, preferred_host_id: str | None) -> list[HostView]:
    hosts = list(view.hosts)
    pick = preferred_host_id or view.preferred_host_id
    if not pick:
        return hosts
    chosen = [h for h in hosts if h.id == pick]
    rest = [h for h in hosts if h.id != pick]
    if not chosen:
        raise ConnectionRuleError("invalid_preferred")
    return chosen + rest
