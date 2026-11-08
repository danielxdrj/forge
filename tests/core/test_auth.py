"""Autenticação humana (ADR-014): device flow com transporte falso, papéis por operação, bootstrap e CLI.

Nenhuma rede. Nenhum OAuth App. Só o transporte HTTP é falso; o resto é o código real.
"""
import hashlib
import json
import logging
import threading
import urllib.error

import pytest

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, actor, login
from forge_core.auth import cli
from forge_core.auth.github import DeviceCode, DeviceFlow, DeviceFlowError, UrllibTransport
from forge_core.auth.store import ORCHESTRATOR_SYSTEM, AuthStore, Principal, SystemActor
from forge_core.errors import AuthenticationError, AuthorizationError, ConfigError
from forge_core.storage import open_repository
from forge_core.tasks import TaskService, TaskStatus as S

SECRET_TOKEN = "gho_SENTINELA_" + "x" * 30


def _flow(gh, clock=None):
    now = [0.0]
    waits = []
    return DeviceFlow(TEST_CLIENT_ID, gh, sleep=waits.append, clock=clock or (lambda: now[0])), waits, now


class Scripted(FakeGitHub):
    def __init__(self, replies, token=SECRET_TOKEN, user=(42, "maria")):
        super().__init__()
        self._replies = list(replies)
        self._token = token
        self._user = user

    def post_form(self, url, data):
        if url.endswith("/device/code"):
            return {"device_code": "dc", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device",
                    "expires_in": 60, "interval": 2}
        if self._replies:
            return self._replies.pop(0)
        return {"access_token": self._token}

    def get_json(self, url, token):
        return {"id": self._user[0], "login": self._user[1]}


# --- device flow ---

def test_device_flow_follows_pending_and_slow_down_then_returns_identity():
    gh = Scripted([{"error": "authorization_pending"}, {"error": "slow_down"}, {"error": "authorization_pending"}])
    flow, waits, _ = _flow(gh)
    _dc, ident = flow.login()
    assert (ident.github_id, ident.login) == (42, "maria")
    assert waits == [2.0, 7.0, 7.0]


@pytest.mark.parametrize("error,code", [("access_denied", "denied"), ("expired_token", "expired"),
                                        ("token_expired", "expired"), ("device_flow_disabled", "device_flow_disabled"),
                                        ("incorrect_client_credentials", "client_id_rejected"),
                                        ("incorrect_device_code", "device_code_rejected"),
                                        ("unsupported_grant_type", "device_flow_failed"),
                                        ("qualquer_outro", "device_flow_failed")])
def test_device_flow_terminal_errors_have_fixed_codes(error, code):
    flow, _, _ = _flow(Scripted([{"error": error}]))
    with pytest.raises(DeviceFlowError) as exc:
        flow.login()
    assert exc.value.code == code


def test_device_flow_expires_by_local_deadline_even_while_pending():
    replies = [{"error": "authorization_pending"}] * 100
    gh = Scripted(replies)
    now = [0.0]

    def tick(seconds):
        now[0] += seconds

    flow = DeviceFlow(TEST_CLIENT_ID, gh, sleep=tick, clock=lambda: now[0])
    with pytest.raises(DeviceFlowError) as exc:
        flow.login()
    assert exc.value.code == "expired"


@pytest.mark.parametrize("user", [(True, "maria"), ("42", "maria"), (0, "maria"), (42, ""), (42, "x y"),
                                  (42, "-invalido"), (42, "a" * 40)])
def test_malformed_identity_is_refused(user):
    flow, _, _ = _flow(Scripted([], user=user))
    with pytest.raises(DeviceFlowError) as exc:
        flow.login()
    assert exc.value.code == "malformed_identity"


def test_missing_client_id_is_refused():
    with pytest.raises(DeviceFlowError, match="client_id_missing"):
        DeviceFlow("", Scripted([]))


class _Boom:
    def open(self, req, timeout=None):
        raise urllib.error.URLError("falha de rede com dado sensível: " + SECRET_TOKEN)


def test_network_error_is_sanitized(monkeypatch):
    t = UrllibTransport()
    monkeypatch.setattr(t, "_opener", _Boom())
    with pytest.raises(DeviceFlowError) as exc:
        t.post_form("https://github.com/login/device/code", {"client_id": "x"})
    assert exc.value.code == "network" and SECRET_TOKEN not in repr(exc.value) and SECRET_TOKEN not in str(exc.value)


@pytest.mark.parametrize("url", ["http://github.com/login/device/code", "https://evil.example/login",
                                 "https://github.com.evil.example/x", "ftp://github.com/x"])
def test_real_transport_refuses_other_hosts_and_schemes(url):
    with pytest.raises(DeviceFlowError, match="endpoint_not_allowed"):
        UrllibTransport()._check(url)


def test_real_transport_never_follows_redirects():
    from forge_core.auth.github import _NoRedirect

    assert _NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/") is None


def test_verification_uri_must_be_on_github():
    class BadUri(FakeGitHub):
        def post_form(self, url, data):
            return {"device_code": "d", "user_code": "U", "verification_uri": "https://evil.example/",
                    "expires_in": 10, "interval": 1}

    with pytest.raises(DeviceFlowError, match="malformed_response"):
        DeviceFlow(TEST_CLIENT_ID, BadUri()).start()


# --- bootstrap, sessão e segredos ---

def test_only_hash_of_session_token_is_persisted_and_no_secret_leaks(make_repo, caplog):
    caplog.set_level(logging.DEBUG)
    repo = make_repo()
    gh = Scripted([])
    gh.select = lambda *a: None
    flow = DeviceFlow(TEST_CLIENT_ID, gh, sleep=lambda s: None)
    _dc, ident = flow.login()
    principal, token = AuthStore(repo).bootstrap_owner(ident.github_id, ident.login)
    stored = repo.fetch("SELECT token_hash FROM sessions")
    assert stored == [(hashlib.sha256(token.encode()).hexdigest(),)]
    assert SECRET_TOKEN not in json.dumps(repo.fetch("SELECT * FROM sessions"), default=str)
    dump = repr(repo.list_audit()) + caplog.text
    assert SECRET_TOKEN not in dump and token not in dump


def test_bootstrap_only_once_and_sanitized(make_repo):
    repo = make_repo()
    gh = FakeGitHub()
    actor(repo, "dona")  # primeiro dono já criado pelo elenco de teste (caminho real de bootstrap)
    with pytest.raises(AuthorizationError, match="bootstrap_already_done"):
        AuthStore(repo).bootstrap_owner(9999, "intruso")
    assert repo.fetch("SELECT COUNT(*) FROM bootstrap_owner")[0][0] == 1
    assert not repo.fetch("SELECT 1 FROM identities WHERE github_id = 9999")


def test_concurrent_bootstrap_has_exactly_one_winner(tmp_path):
    url = f"sqlite:///{tmp_path / 'boot.db'}"
    open_repository(url)
    results = []
    barrier = threading.Barrier(4)

    def attempt(gid):
        repo = open_repository(url)
        barrier.wait()
        try:
            AuthStore(repo).bootstrap_owner(gid, f"p{gid}")
            results.append(("ok", gid))
        except AuthorizationError as exc:
            results.append(("refused", str(exc)))

    threads = [threading.Thread(target=attempt, args=(2000 + i,)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert sorted(r[0] for r in results) == ["ok", "refused", "refused", "refused"]
    assert all(r[1] == "bootstrap_already_done" for r in results if r[0] == "refused")
    assert open_repository(url).fetch("SELECT COUNT(*) FROM bootstrap_owner")[0][0] == 1


# --- autorização por operação ---

def test_only_owner_grants_and_revokes(make_repo):
    repo = make_repo()
    ana = actor(repo, "ana")
    store = AuthStore(repo)
    with pytest.raises(AuthorizationError, match="forbidden"):
        store.grant_role(ana, 1002, "editor")
    with pytest.raises(AuthorizationError, match="forbidden"):
        store.grant_role(actor(repo, "chefe"), 1002, "editor")
    gid = repo.fetch("SELECT id FROM role_grants WHERE identity_id = 'gh:1001' AND role = 'editor'")[0][0]
    with pytest.raises(AuthorizationError, match="forbidden"):
        store.revoke_role(ana, gid)


def test_owner_cannot_grant_owner_or_unknown_identity(make_repo):
    repo = make_repo()
    dona = actor(repo, "dona")
    with pytest.raises(AuthorizationError, match="role_unknown"):
        AuthStore(repo).grant_role(dona, 1001, "owner")
    with pytest.raises(AuthorizationError, match="identity_unknown"):
        AuthStore(repo).grant_role(dona, 77777, "editor")


def test_last_owner_cannot_be_revoked(make_repo):
    repo = make_repo()
    dona = actor(repo, "dona")
    gid = repo.fetch("SELECT id FROM role_grants WHERE role = 'owner'")[0][0]
    with pytest.raises(AuthorizationError, match="last_owner"):
        AuthStore(repo).revoke_role(dona, gid)


def test_revocation_takes_effect_on_the_next_operation(make_repo):
    repo = make_repo()
    dona = actor(repo, "dona")
    svc = TaskService(repo)
    ana = actor(repo, "ana")
    t = svc.create_task("antes", ana)
    gid = repo.fetch("SELECT id FROM role_grants WHERE identity_id = 'gh:1001' AND role = 'editor'")[0][0]
    AuthStore(repo).revoke_role(dona, gid)
    with pytest.raises(AuthorizationError, match="forbidden"):
        svc.update_task(t.id, ana, 1, title="depois")
    assert svc.get_task(t.id).title == "antes"


def test_logout_revokes_session_for_every_later_operation(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    ana = actor(repo, "ana")
    AuthStore(repo).revoke_session(ana)
    with pytest.raises(AuthenticationError, match="invalid_session"):
        svc.create_task("depois do logout", ana)
    with pytest.raises(AuthenticationError, match="invalid_session"):
        AuthStore(repo).require(ana, "editor")


def test_text_and_forged_objects_grant_no_authority(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    for fake in ("pessoa:dona", "gh:1000", "sistema:orchestrator", None, {"identity_id": "gh:1000"}):
        with pytest.raises(AuthenticationError, match="principal_missing"):
            svc.create_task("x", fake)
    with pytest.raises(AuthenticationError, match="principal_forged"):
        Principal("gh:1000", "dona", "sessao", _issued=object())


def test_system_actor_only_moves_status_and_never_edits_or_approves(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(repo, "ana"))
    svc.change_status(t.id, S.IN_PROGRESS, ORCHESTRATOR_SYSTEM)
    assert svc.changes(t.id)[-1].actor == "sistema:orchestrator"
    with pytest.raises(AuthenticationError, match="principal_missing"):
        svc.update_task(t.id, ORCHESTRATOR_SYSTEM, 2, title="sistema editando")
    with pytest.raises(AuthenticationError, match="principal_missing"):
        svc.create_task("nova", SystemActor("orchestrator"))


def test_principal_from_another_database_is_rejected(make_repo, tmp_path):
    repo_a = make_repo()
    other = open_repository(f"sqlite:///{tmp_path / 'outro.db'}")
    ana_a = actor(repo_a, "ana")
    with pytest.raises(AuthenticationError):
        AuthStore(other).require(ana_a, "editor")


def test_auth_tables_are_append_only_sqlite(tmp_path):
    import sqlite3

    repo = open_repository(f"sqlite:///{tmp_path / 'ap.db'}")
    actor(repo, "dona")
    updates = {"identities": "login = login", "role_grants": "role = role", "sessions": "login = login",
               "bootstrap_owner": "at = at"}
    for table, col in updates.items():
        for sql in (f"UPDATE {table} SET {col}", f"DELETE FROM {table}"):
            with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                repo._conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE role_grants SET role = 'owner'", "DELETE FROM sessions",
                                 "TRUNCATE approval_grants"])
def test_auth_tables_are_append_only_and_writer_cannot_change_them_postgres(pg_env, sql):
    import psycopg

    writer, owner, _ = pg_env
    actor(writer, "dona")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner._run([(sql, ())])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])


# --- CLI local ---

@pytest.fixture
def cli_env(tmp_path):
    return {
        "FORGE_CONFIG_DIR": str(tmp_path / "cfg"),
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'cli.db'}",
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_SESSION_FILE": str(tmp_path / "sessao" / "session.json"),
    }


def test_cli_bootstrap_whoami_grant_logout_flow(cli_env, tmp_path, capsys):
    gh = Scripted([], token=SECRET_TOKEN, user=(42, "maria"))
    out, err = _Buf(), _Buf()
    assert cli.run(["bootstrap"], cli_env, transport=gh, out=out, err=err) == 0
    session = tmp_path / "sessao" / "session.json"
    assert oct(session.stat().st_mode & 0o777) == "0o600"
    assert "ABCD-1234" in out.text and SECRET_TOKEN not in out.text + err.text

    out2 = _Buf()
    assert cli.run(["whoami"], cli_env, out=out2) == 0
    info = json.loads(out2.text)
    assert info["login"] == "maria" and info["identity"] == "gh:42" and info["roles"] == ["owner"]

    assert cli.run(["grant", "--github-id", "1001", "--role", "editor"], cli_env, out=_Buf()) == 1  # gh:1001 não entrou
    assert cli.run(["logout"], cli_env, out=_Buf()) == 0
    assert not session.exists()
    err3 = _Buf()
    assert cli.run(["whoami"], cli_env, out=_Buf(), err=err3) == 1
    assert "sessao_ausente" in err3.text


def test_cli_errors_print_codes_only(cli_env, tmp_path):
    class Boom(FakeGitHub):
        def post_form(self, url, data):
            raise DeviceFlowError("network")

    err = _Buf()
    assert cli.run(["login"], cli_env, transport=Boom(), out=_Buf(), err=err) == 1
    assert "network" in err.text and "Traceback" not in err.text


def test_cli_refuses_missing_client_id(cli_env):
    env = dict(cli_env)
    env.pop("FORGE_GITHUB_CLIENT_ID")
    err = _Buf()
    assert cli.run(["bootstrap"], env, transport=Scripted([]), out=_Buf(), err=err) == 1
    assert "FORGE_GITHUB_CLIENT_ID" in err.text


class _Buf:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass
