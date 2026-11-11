import pytest

from auth_helpers import FakeGitHub, bootstrap, login, oauth_token
from forge_core.auth.store import AuthStore
from forge_core.errors import AuthenticationError, AuthorizationError
from forge_core.web.security import require_editor


def test_web_session_expires_cli_null_does_not(make_repo):
    repo = make_repo()
    now = ["2026-01-01T00:00:00+00:00"]
    gh = FakeGitHub()
    flow, oauth = oauth_token(gh, "maria", 42)
    store = AuthStore(repo, verify=flow.identity, clock=lambda: now[0])
    _principal, web_token = store.open_session(oauth, expires_at="2026-01-01T01:00:00+00:00")
    _p2, cli_token = store.open_session(oauth)
    store.resolve_session(web_token)
    store.resolve_session(cli_token)
    now[0] = "2026-01-01T02:00:00+00:00"
    with pytest.raises(AuthenticationError, match="invalid_session"):
        store.resolve_session(web_token)
    store.resolve_session(cli_token)


def test_owner_does_not_imply_editor(make_repo):
    repo = make_repo()
    owner = bootstrap(repo, FakeGitHub())
    store = AuthStore(repo)
    assert store.has_role(owner.identity_id, "owner")
    with pytest.raises(AuthorizationError, match="forbidden"):
        require_editor(store, owner)


def test_revoked_session_rejected_before_expiry(make_repo):
    repo = make_repo()
    gh = FakeGitHub()
    flow, oauth = oauth_token(gh, "maria", 42)
    store = AuthStore(repo, verify=flow.identity)
    principal, token = store.open_session(oauth, expires_at="2099-01-01T00:00:00+00:00")
    store.revoke_session(principal)
    with pytest.raises(AuthenticationError, match="invalid_session"):
        store.resolve_session(token)


def test_session_survives_store_restart(make_repo):
    repo = make_repo()
    gh = FakeGitHub()
    flow, oauth = oauth_token(gh, "maria", 42)
    store = AuthStore(repo, verify=flow.identity)
    _principal, token = store.open_session(oauth, expires_at="2099-01-01T00:00:00+00:00")
    again = AuthStore(repo)
    principal = again.resolve_session(token)
    assert principal.login == "maria"
    dump = repr(repo.fetch("SELECT * FROM sessions"))
    assert "gho_" not in dump
    assert token not in dump


def test_sliding_renewal_extends_expiry_after_half_ttl(make_repo):
    repo = make_repo()
    now = ["2026-01-01T00:00:00+00:00"]
    gh = FakeGitHub()
    flow, oauth = oauth_token(gh, "maria", 42)
    store = AuthStore(repo, verify=flow.identity, clock=lambda: now[0])
    principal, token = store.open_session(oauth, expires_at="2026-01-01T00:02:00+00:00")
    now[0] = "2026-01-01T00:00:50+00:00"
    assert store.touch_session(principal, 120) == "2026-01-01T00:02:00+00:00"
    now[0] = "2026-01-01T00:01:10+00:00"
    renewed = store.touch_session(principal, 120)
    assert renewed == "2026-01-01T00:03:10+00:00"
    now[0] = "2026-01-01T00:02:30+00:00"
    store.resolve_session(token)
    now[0] = "2026-01-01T00:03:11+00:00"
    with pytest.raises(AuthenticationError, match="invalid_session"):
        store.resolve_session(token)


def test_revoke_role_invalidates_that_identity_sessions(make_repo):
    repo = make_repo()
    owner = bootstrap(repo, FakeGitHub())
    gh = FakeGitHub()
    ana = login(repo, gh, "ana", 1001)
    AuthStore(repo).grant_role(owner, 1001, "editor")
    flow, oauth = oauth_token(gh, "ana", 1001)
    store = AuthStore(repo, verify=flow.identity)
    _p, token = store.open_session(oauth, expires_at="2099-01-01T00:00:00+00:00")
    store.resolve_session(token)
    gid = repo.fetch("SELECT id FROM role_grants WHERE identity_id = 'gh:1001' AND role = 'editor'")[0][0]
    AuthStore(repo).revoke_role(owner, gid)
    with pytest.raises(AuthenticationError, match="invalid_session"):
        store.resolve_session(token)
