"""CLI local de autenticação humana (ADR-014). Só linha de comando, sem servidor nem interface web.

Comandos: bootstrap (primeiro dono, uma vez), login, whoami, logout, grant, revoke.
O código de verificação do device flow é mostrado no terminal de quem executa, e só lá.
A sessão fica em arquivo local com permissão 0600; o banco guarda só o hash do token.
Erros saem com código fixo, sem token, sem código de device e sem traceback.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from ..config import load_settings
from ..errors import AuthenticationError, AuthorizationError, ConfigError, ForgeError
from ..storage.sql import open_repository
from .github import DeviceFlow, DeviceFlowError, Transport, UrllibTransport
from .store import AuthStore, Principal


def default_session_file(env: Mapping[str, str]) -> Path:
    if env.get("FORGE_SESSION_FILE"):
        return Path(env["FORGE_SESSION_FILE"])
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "forge" / "session.json"


def _write_session(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"token": token}, fh)
    os.replace(tmp, path)


def _read_session(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        token = data["token"]
    except (OSError, ValueError, KeyError, TypeError):
        raise AuthenticationError("sessao_ausente") from None
    if not isinstance(token, str) or not token:
        raise AuthenticationError("sessao_ausente")
    return token


def _login(repo, flow: DeviceFlow, out) -> tuple[Principal, str]:
    dc = flow.start()
    print(f"Abra {dc.verification_uri} e informe o código: {dc.user_code}", file=out)
    token = flow.poll_token(dc)
    ident = flow.identity(token)
    store = AuthStore(repo)
    return store.open_session(ident.github_id, ident.login)


def run(argv: list[str], env: Mapping[str, str] | None = None, transport: Transport | None = None,
        out=None, err=None) -> int:
    env = os.environ if env is None else env
    out = out or sys.stdout
    err = err or sys.stderr
    parser = argparse.ArgumentParser(prog="forge-auth", description="Autenticação humana do Forge (ADR-014).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap", help="primeiro dono da instalação (uma vez)")
    sub.add_parser("login", help="abre sessão local")
    sub.add_parser("whoami", help="mostra a identidade da sessão atual")
    sub.add_parser("logout", help="revoga a sessão atual")
    g = sub.add_parser("grant", help="concede papel (owner)")
    g.add_argument("--github-id", type=int, required=True)
    g.add_argument("--role", required=True, choices=("editor", "approver"))
    r = sub.add_parser("revoke", help="revoga concessão de papel (owner)")
    r.add_argument("--grant-id", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        settings = load_settings(env)
        if not settings.database_url:
            raise ConfigError("FORGE_DATABASE_URL é obrigatória")
        if not settings.github_client_id and args.cmd in ("bootstrap", "login"):
            raise ConfigError("FORGE_GITHUB_CLIENT_ID é obrigatória para entrar")
        repo = open_repository(settings.database_url, settings.database_migration_url)
        session_path = default_session_file(env)
        store = AuthStore(repo)

        if args.cmd in ("bootstrap", "login"):
            flow = DeviceFlow(settings.github_client_id, transport or UrllibTransport())
            if args.cmd == "bootstrap":
                dc = flow.start()
                print(f"Abra {dc.verification_uri} e informe o código: {dc.user_code}", file=out)
                token = flow.poll_token(dc)
                ident = flow.identity(token)
                principal, session_token = store.bootstrap_owner(ident.github_id, ident.login)
            else:
                principal, session_token = _login(repo, flow, out)
            _write_session(session_path, session_token)
            print(f"Sessão aberta para {principal.login}.", file=out)
            return 0

        principal = store.resolve_session(_read_session(session_path))
        if args.cmd == "whoami":
            roles = [r for r in ("owner", "editor", "approver") if store.has_role(principal.identity_id, r)]
            print(json.dumps({"login": principal.login, "identity": principal.identity_id, "roles": roles}),
                  file=out)
        elif args.cmd == "logout":
            store.revoke_session(principal)
            session_path.unlink(missing_ok=True)
            print("Sessão revogada.", file=out)
        elif args.cmd == "grant":
            store.grant_role(principal, args.github_id, args.role)
            print("Papel concedido.", file=out)
        elif args.cmd == "revoke":
            store.revoke_role(principal, args.grant_id)
            print("Papel revogado.", file=out)
        return 0
    except DeviceFlowError as exc:
        print(f"forge-auth: falha no login ({exc.code})", file=err)
    except (AuthenticationError, AuthorizationError, ConfigError) as exc:
        print(f"forge-auth: {exc}", file=err)
    except ForgeError as exc:
        print(f"forge-auth: erro ({type(exc).__name__})", file=err)
    return 1


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
