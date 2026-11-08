"""Pessoas de teste autenticadas pelo caminho REAL (device flow + sessão + verificação de token).

Só o transporte HTTP é falso. Nenhuma rede, nenhum OAuth App, nenhum Principal criado direto.
"""
from forge_core.auth.github import DeviceFlow, GitHubIdentity
from forge_core.auth.store import AuthStore

TEST_CLIENT_ID = "test-client-id-nao-real"


class FakeGitHub:
    def __init__(self):
        self.users: dict[str, GitHubIdentity] = {}
        self.outcomes: list[str] = []  # respostas do polling, ex. ["authorization_pending", "slow_down"]

    def register(self, login: str, github_id: int) -> str:
        token = f"tok-{github_id}"
        self.users[token] = GitHubIdentity(github_id, login)
        return token

    def post_form(self, url, data):
        if url.endswith("/device/code"):
            return {"device_code": "dc-teste", "user_code": "TEST-0000",
                    "verification_uri": "https://github.com/login/device", "expires_in": 900, "interval": 1}
        if self.outcomes:
            return {"error": self.outcomes.pop(0)}
        return {"access_token": self._pending_token}

    def get_json(self, url, token):
        ident = self.users[token]
        return {"id": ident.github_id, "login": ident.login}

    _pending_token = ""

    def select(self, login: str, github_id: int) -> None:
        self._pending_token = self.register(login, github_id)


def oauth_token(gh: FakeGitHub, login_name: str, github_id: int):
    """Token OAuth obtido pelo device flow falso. Só isto entra no store; id e login vêm do GitHub."""
    gh.select(login_name, github_id)
    flow = DeviceFlow(TEST_CLIENT_ID, gh, sleep=lambda s: None)
    return flow, flow.poll_token(flow.start())


def login(repo, gh: FakeGitHub, login_name: str, github_id: int):
    """Login verificado: device flow falso, sessão nova, e resolução do token de sessão no banco."""
    flow, oauth = oauth_token(gh, login_name, github_id)
    _principal, session_token = AuthStore(repo, verify=flow.identity).open_session(oauth)
    return AuthStore(repo).resolve_session(session_token)


def bootstrap(repo, gh: FakeGitHub, login_name: str = "dona", github_id: int = 1000):
    flow, oauth = oauth_token(gh, login_name, github_id)
    principal, _token = AuthStore(repo, verify=flow.identity).bootstrap_owner(oauth, github_id)
    return principal


def person(repo, owner, gh: FakeGitHub, login_name: str, github_id: int, *roles: str):
    p = login(repo, gh, login_name, github_id)
    for role in roles:
        AuthStore(repo).grant_role(owner, github_id, role)
    return p


ROSTER = {
    "dona": (1000, ()),          # owner (bootstrap)
    "ana": (1001, ("editor",)),
    "bia": (1002, ("editor",)),
    "chefe": (1003, ("approver",)),
    "solta": (1004, ()),         # autenticada, sem papel
}
_cache: dict = {}


def _has_owner(repo) -> bool:
    return bool(repo.fetch("SELECT 1 FROM bootstrap_owner"))


def actor(obj, name: str):
    """Pessoa de teste autenticada no banco de `obj` (repo ou serviço). Cria o elenco na primeira vez.

    Se o banco já tem dono (outro objeto abriu o mesmo arquivo), entra por login, sem novo bootstrap.
    """
    repo = getattr(obj, "_repo", obj)
    if repo not in _cache:
        gh = FakeGitHub()
        people = {}
        for pname, (gid, roles) in ROSTER.items():
            if pname == "dona" and not _has_owner(repo):
                people[pname] = bootstrap(repo, gh, pname, gid)
                continue
            people[pname] = login(repo, gh, pname, gid)
            if pname == "dona":
                continue
            for role in roles:
                if not AuthStore(repo).has_role(people[pname].identity_id, role):
                    AuthStore(repo).grant_role(people["dona"] if "dona" in people else
                                               login(repo, gh, "dona", ROSTER["dona"][0]), gid, role)
        _cache[repo] = people
    return _cache[repo][name]
