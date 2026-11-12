"""Cadastro de conexões, cofre Fernet e teste com rede falsa."""
from __future__ import annotations

import pytest

cryptography = pytest.importorskip("cryptography")
from cryptography.fernet import Fernet

from forge_core.auth.store import AuthStore
from forge_core.connections.probes import ConnectionProbes, ProbeError
from forge_core.connections.service import ConnectionRuleError, ConnectionService
from forge_core.connections.vault import ConnectionsVault
from forge_core.errors import AuthorizationError
from forge_core.storage.migrate import pending_migrations
from auth_helpers import actor


SECRET = "senha-ficticia-nao-usar"


def _vault(tmp_path):
    key_file = tmp_path / "forge_connections_key"
    key_file.write_bytes(Fernet.generate_key())
    key_file.chmod(0o600)
    return ConnectionsVault.from_key_file(str(key_file)), key_file


def _payload(**overrides):
    data = {
        "name": "erp",
        "type": "postgres",
        "user": "consulta",
        "port": 5432,
        "database": "app",
        "hosts": [
            {"label": "tailscale", "host": "100.64.0.10", "order": 0},
            {"label": "empresa", "host": "db.example.invalid", "order": 1},
        ],
        "preferred_index": 0,
    }
    data.update(overrides)
    return data


class FakeProbes:
    def __init__(self, outcomes=None):
        self.outcomes = dict(outcomes or {})
        self.calls = []

    def test_one(self, conn_type, host, port, username, secret, database, remote_path):
        self.calls.append({
            "type": conn_type, "host": host, "port": port, "user": username,
            "database": database, "path": remote_path, "secret": secret,
        })
        outcome = self.outcomes.get(host)
        if isinstance(outcome, ProbeError):
            raise outcome


def test_0015_listed_for_both_dialects_and_tables_exist(make_repo):
    sqlite = [p.stem for p in pending_migrations("sqlite")]
    postgres = [p.stem for p in pending_migrations("postgres")]
    assert any(s.startswith("0015_connections") for s in sqlite)
    assert any(s.startswith("0015_connections") for s in postgres)
    repo = make_repo()
    repo.fetch("SELECT id, name, type, username, port, database_name, remote_path, secret_ciphertext, preferred_host_id FROM connections LIMIT 0")
    repo.fetch("SELECT id, connection_id, label, hostname, sort_order FROM connection_hosts LIMIT 0")


def test_vault_missing_or_invalid_is_disabled(tmp_path):
    missing = ConnectionsVault.from_key_file(str(tmp_path / "forge_connections_key"))
    assert not missing.enabled
    assert missing.reason == "vault_disabled"
    bad = tmp_path / "forge_connections_key"
    bad.write_text("nao-e-uma-chave", encoding="utf-8")
    invalid = ConnectionsVault.from_key_file(str(bad))
    assert not invalid.enabled
    assert invalid.reason == "vault_invalid"
    env = {"FORGE_SECRET_CONNECTIONS_KEY_FILE": ""}
    assert not ConnectionsVault.from_env(env).enabled


def test_owner_crud_encrypts_secret_and_never_returns_it(make_repo, tmp_path):
    repo = make_repo()
    vault, _ = _vault(tmp_path)
    svc = ConnectionService(repo, AuthStore(repo), vault, FakeProbes())
    owner = actor(repo, "dona")
    editor = actor(repo, "ana")
    created = svc.create(owner, _payload(), SECRET)
    assert created.secret_set is True
    blob = created.as_json()
    assert "secret" not in blob or blob.get("secret") in (None, True, False)
    assert SECRET not in repr(blob)
    assert blob["user"] == "consulta"
    assert blob["hosts"][0]["host"] == "100.64.0.10"
    rows = repo.fetch("SELECT secret_ciphertext FROM connections WHERE id=?", (created.id,))
    assert rows[0][0]
    assert SECRET not in rows[0][0]
    listed = svc.list_connections(editor)
    assert listed[0].id == created.id
    assert listed[0].secret_set is True
    before = repo.fetch("SELECT secret_ciphertext FROM connections WHERE id=?", (created.id,))[0][0]
    updated = svc.update(owner, created.id, _payload(name="erp-lab"), None)
    assert updated.name == "erp-lab"
    assert updated.secret_set is True
    after = repo.fetch("SELECT secret_ciphertext FROM connections WHERE id=?", (created.id,))[0][0]
    assert after == before
    dump = repr(repo.fetch("SELECT * FROM connections")) + repr(repo.list_audit())
    assert SECRET not in dump
    assert "senha-ficticia" not in dump
    with pytest.raises(AuthorizationError):
        svc.create(editor, _payload(name="outra"), SECRET)
    svc.delete(owner, created.id)
    assert svc.list_connections(editor) == []


def test_editor_lists_and_tests_hosts_in_order(make_repo, tmp_path):
    repo = make_repo()
    vault, _ = _vault(tmp_path)
    probes = FakeProbes({
        "100.64.0.10": ProbeError("timeout"),
        "db.example.invalid": None,
    })
    svc = ConnectionService(repo, AuthStore(repo), vault, probes)
    owner = actor(repo, "dona")
    editor = actor(repo, "ana")
    created = svc.create(owner, _payload(), SECRET)
    result = svc.test(editor, created.id)
    assert result["ok"] is True
    assert result["host"] == "db.example.invalid"
    assert probes.calls[0]["host"] == "100.64.0.10"
    assert probes.calls[1]["host"] == "db.example.invalid"
    assert probes.calls[0]["secret"] == SECRET
    assert SECRET not in result["message"]
    audit = repr(repo.list_audit())
    assert SECRET not in audit
    assert "connection.test" in [a.action for a in repo.list_audit()]
    with pytest.raises(AuthorizationError):
        svc.delete(editor, created.id)


def test_without_vault_area_is_disabled(make_repo):
    repo = make_repo()
    svc = ConnectionService(repo, AuthStore(repo), ConnectionsVault.disabled(), FakeProbes())
    owner = actor(repo, "dona")
    status = svc.status()
    assert status["enabled"] is False
    assert "chave" in status["message"].lower() or "desligada" in status["message"].lower()
    with pytest.raises(ConnectionRuleError, match="vault_disabled"):
        svc.create(owner, _payload(), SECRET)


def test_sftp_banner_and_portainer_token_header(monkeypatch):
    class Sock:
        def settimeout(self, t):
            self.timeout = t

        def recv(self, n):
            return b"SSH-2.0-OpenSSH_9.2\r\n"

        def close(self):
            pass

    monkeypatch.setattr(
        "forge_core.connections.probes.socket.create_connection",
        lambda addr, timeout: Sock(),
    )
    ConnectionProbes(timeout=1).test_one("sftp", "ftp.example.invalid", 22, "u", "x", None, "/logs")

    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["key"] = req.headers.get("X-api-key") or req.headers.get("X-API-Key")
        return Resp()

    ConnectionProbes(timeout=1, urlopen_fn=fake_urlopen).test_one(
        "portainer", "portainer.example.invalid", 9000, "admin", "token-ficticio", None, None,
    )
    assert seen["url"].startswith("http://portainer.example.invalid:9000/api/status")
    assert seen["key"] == "token-ficticio"
