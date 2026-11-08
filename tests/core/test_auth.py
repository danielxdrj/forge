"""Autenticação humana (ADR-014): device flow com transporte falso, papéis por operação, bootstrap e CLI.

Nenhuma rede. Nenhum OAuth App. Só o transporte HTTP é falso; o resto é o código real.
"""
import hashlib
import json
import logging
import threading
import urllib.error

import pytest

from auth_helpers import TEST_CLIENT_ID, FakeGitHub, actor, oauth_token
from forge_core.auth import cli
from forge_core.auth.github import DeviceFlow, DeviceFlowError, UrllibTransport
from forge_core.auth.github import GitHubIdentity
from forge_core.auth.store import AuthStore, Principal
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
    flow = DeviceFlow(TEST_CLIENT_ID, gh, sleep=lambda s: None)
    oauth = flow.poll_token(flow.start())
    principal, token = AuthStore(repo, verify=flow.identity).bootstrap_owner(oauth, 42)
    stored = repo.fetch("SELECT token_hash FROM sessions")
    assert stored == [(hashlib.sha256(token.encode()).hexdigest(),)]
    assert SECRET_TOKEN not in json.dumps(repo.fetch("SELECT * FROM sessions"), default=str)
    assert SECRET_TOKEN not in json.dumps(repo.fetch("SELECT * FROM identities"), default=str)
    dump = repr(repo.list_audit()) + caplog.text
    assert SECRET_TOKEN not in dump and token not in dump


def test_bootstrap_only_once_and_sanitized(make_repo):
    repo = make_repo()
    gh = FakeGitHub()
    actor(repo, "dona")  # primeiro dono já criado pelo elenco de teste (caminho real de bootstrap)
    flow, oauth = oauth_token(gh, "intruso", 9999)
    with pytest.raises(AuthorizationError, match="bootstrap_already_done"):
        AuthStore(repo, verify=flow.identity).bootstrap_owner(oauth, 9999)
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
            AuthStore(repo, verify=lambda t: GitHubIdentity(int(t), f"p{t}")).bootstrap_owner(str(gid), gid)
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


class _FakeSystem:
    """Objeto fabricado pelo chamador, com a mesma forma que um sistema antigo tinha."""
    name = "orchestrator"
    identity_id = "sistema:orchestrator"


@pytest.mark.parametrize("fake", ["sistema:orchestrator", "agente:triagem", _FakeSystem(),
                                  {"identity_id": "gh:1000"}, None])
def test_status_change_refuses_text_and_fabricated_actors(make_repo, fake):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(repo, "ana"))
    with pytest.raises(AuthenticationError, match="principal_missing"):
        svc.change_status(t.id, S.IN_PROGRESS, fake)
    assert svc.get_task(t.id).status == S.PENDING
    assert not any(c.actor.startswith("sistema:") for c in svc.changes(t.id))


def test_status_change_by_person_without_editor_role_is_refused(make_repo):
    repo = make_repo()
    svc = TaskService(repo)
    t = svc.create_task("t", actor(repo, "ana"))
    with pytest.raises(AuthorizationError, match="forbidden"):
        svc.change_status(t.id, S.IN_PROGRESS, actor(repo, "solta"))
    assert svc.get_task(t.id).status == S.PENDING


def test_direct_session_and_bootstrap_calls_cannot_choose_an_identity(make_repo):
    repo = make_repo()
    gh = FakeGitHub()
    flow, oauth = oauth_token(gh, "eva", 555)
    store = AuthStore(repo, verify=flow.identity)
    with pytest.raises(TypeError):
        store.open_session(1000, "dona")  # sem id/login de entrada
    with pytest.raises(AuthenticationError, match="invalid_identity"):
        store.bootstrap_owner(1000, 1000)  # token não string nunca vira identidade
    assert repo.fetch("SELECT COUNT(*) FROM bootstrap_owner")[0][0] == 0
    with pytest.raises(ConfigError):
        AuthStore(repo).open_session(oauth)  # sem verificador, não emite sessão
    with pytest.raises(AuthenticationError, match="invalid_identity"):
        store.open_session("")
    assert repo.fetch("SELECT COUNT(*) FROM sessions")[0][0] == 0


def test_bootstrap_with_verified_identity_other_than_expected_writes_nothing(make_repo):
    repo = make_repo()
    gh = FakeGitHub()
    flow, oauth = oauth_token(gh, "eva", 555)
    with pytest.raises(AuthenticationError, match="bootstrap_identity_mismatch"):
        AuthStore(repo, verify=flow.identity).bootstrap_owner(oauth, 1000)
    assert repo.fetch("SELECT COUNT(*) FROM bootstrap_owner")[0][0] == 0
    assert repo.fetch("SELECT COUNT(*) FROM role_grants")[0][0] == 0
    assert repo.fetch("SELECT COUNT(*) FROM sessions")[0][0] == 0


def test_verifier_decides_identity_not_the_caller(make_repo):
    repo = make_repo()
    store = AuthStore(repo, verify=lambda token: GitHubIdentity(777, "nome-real"))
    principal, _ = store.open_session("qualquer-token")
    assert (principal.identity_id, principal.login) == ("gh:777", "nome-real")


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
    # TRUNCATE em tabela referenciada por FK é recusado pelo próprio Postgres, antes do gatilho: continua bloqueado.
    with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.FeatureNotSupported), match="append-only|foreign key|truncate|TRUNCATE"):
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
    }


def _files_under(root):
    return [p for p in root.rglob("*") if p.is_file() and p.name != "cli.db"]


def test_cli_bootstrap_only_for_expected_identity_and_no_session_file(cli_env, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    gh = Scripted([], token=SECRET_TOKEN, user=(42, "maria"))
    out, err = _Buf(), _Buf()
    assert cli.run(["bootstrap", "--expect-github-id", "42"], cli_env, transport=gh, out=out, err=err) == 0
    assert "ABCD-1234" in out.text and SECRET_TOKEN not in out.text + err.text
    assert _files_under(tmp_path) == []
    assert SECRET_TOKEN not in caplog.text

    repo = open_repository(cli_env["FORGE_DATABASE_URL"])
    assert repo.fetch("SELECT COUNT(*) FROM sessions")[0][0] == repo.fetch(
        "SELECT COUNT(*) FROM session_revocations")[0][0] == 1
    assert SECRET_TOKEN not in repr(repo.list_audit())

    out2 = _Buf()
    assert cli.run(["whoami"], cli_env, transport=Scripted([], token="outro-token", user=(42, "maria")),
                   out=out2) == 0
    info = json.loads(out2.text.strip().splitlines()[-1])
    assert info["login"] == "maria" and info["identity"] == "gh:42" and info["roles"] == ["owner"]


def test_cli_bootstrap_refuses_other_identity_without_writing(cli_env):
    gh = Scripted([], token=SECRET_TOKEN, user=(42, "maria"))
    err = _Buf()
    assert cli.run(["bootstrap", "--expect-github-id", "99"], cli_env, transport=gh, out=_Buf(), err=err) == 1
    assert "bootstrap_identity_mismatch" in err.text and SECRET_TOKEN not in err.text
    repo = open_repository(cli_env["FORGE_DATABASE_URL"])
    assert repo.fetch("SELECT COUNT(*) FROM bootstrap_owner")[0][0] == 0
    assert repo.fetch("SELECT COUNT(*) FROM sessions")[0][0] == 0


def test_cli_bootstrap_refused_before_login_when_already_done(cli_env):
    gh = Scripted([], token=SECRET_TOKEN, user=(42, "maria"))
    assert cli.run(["bootstrap", "--expect-github-id", "42"], cli_env, transport=gh, out=_Buf(), err=_Buf()) == 0
    err = _Buf()
    assert cli.run(["bootstrap", "--expect-github-id", "42"], cli_env, transport=gh, out=_Buf(), err=err) == 1
    assert "bootstrap_already_done" in err.text


def test_cli_whoami_shows_no_roles_and_revokes_its_session(cli_env):
    gh = Scripted([], token=SECRET_TOKEN, user=(7, "joao"))
    out, err = _Buf(), _Buf()
    assert cli.run(["whoami"], cli_env, transport=gh, out=out, err=err) == 0
    assert json.loads(out.text.strip().splitlines()[-1])["roles"] == []
    assert SECRET_TOKEN not in out.text + err.text
    repo = open_repository(cli_env["FORGE_DATABASE_URL"])
    assert repo.fetch("SELECT COUNT(*) FROM sessions")[0][0] == repo.fetch(
        "SELECT COUNT(*) FROM session_revocations")[0][0] == 1


def test_cli_errors_print_codes_only(cli_env, tmp_path):
    class Boom(FakeGitHub):
        def post_form(self, url, data):
            raise DeviceFlowError("network")

    err = _Buf()
    assert cli.run(["whoami"], cli_env, transport=Boom(), out=_Buf(), err=err) == 1
    assert "network" in err.text and "Traceback" not in err.text


def test_cli_refuses_missing_client_id(cli_env):
    env = dict(cli_env)
    env.pop("FORGE_GITHUB_CLIENT_ID")
    err = _Buf()
    assert cli.run(["bootstrap", "--expect-github-id", "42"], env, transport=Scripted([]), out=_Buf(),
                   err=err) == 1
    assert "FORGE_GITHUB_CLIENT_ID" in err.text


class _Buf:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass
