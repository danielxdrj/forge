import pytest

from auth_helpers import FakeGitHub, bootstrap, oauth_token
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
