"""CLI local de autenticação humana (ADR-014). Só linha de comando, sem servidor nem interface web.

Comandos: bootstrap (primeiro dono, uma vez, com identidade esperada), whoami, grant, revoke.
Não há arquivo de sessão. Cada comando faz seu próprio login (device flow), executa a operação
com a sessão mantida só em memória e revoga essa sessão ao terminar. Nenhum bearer fica no disco.
O código de verificação do device flow é mostrado no terminal de quem executa, e só lá.
Erros saem com código fixo, sem token, sem código de device e sem traceback.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping

from ..config import load_settings
from ..errors import AuthenticationError, AuthorizationError, ConfigError, ForgeError
from ..storage.sql import open_repository
from .github import DeviceFlow, DeviceFlowError, Transport, UrllibTransport
from .store import AuthStore, Principal


def _announce(flow: DeviceFlow, out) -> str:
    dc = flow.start()
    print(f"Abra {dc.verification_uri} e informe o código: {dc.user_code}", file=out)
    return flow.poll_token(dc)


def _with_login(store: AuthStore, flow: DeviceFlow, out, operation: Callable[[Principal], int]) -> int:
    principal, _session_token = store.open_session(_announce(flow, out))
    try:
        return operation(principal)
    finally:
        store.revoke_session(principal)


def _bootstrap(store: AuthStore, flow: DeviceFlow, expected_github_id: int, out) -> int:
    if store.has_owner():
        raise AuthorizationError("bootstrap_already_done")
    principal, _session_token = store.bootstrap_owner(_announce(flow, out), expected_github_id)
    try:
        print(f"Dono inicial criado: {principal.login}.", file=out)
    finally:
        store.revoke_session(principal)
    return 0


def run(argv: list[str], env: Mapping[str, str] | None = None, transport: Transport | None = None,
        out=None, err=None) -> int:
    env = os.environ if env is None else env
    out = out or sys.stdout
    err = err or sys.stderr
    parser = argparse.ArgumentParser(prog="forge-auth", description="Autenticação humana do Forge (ADR-014).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap", help="primeiro dono da instalação (uma vez)")
    b.add_argument("--expect-github-id", type=int, required=True,
                   help="id numérico do GitHub que o operador autoriza como dono inicial")
    sub.add_parser("whoami", help="entra e mostra a identidade e os papéis")
    g = sub.add_parser("grant", help="entra como owner e concede papel")
    g.add_argument("--github-id", type=int, required=True)
    g.add_argument("--role", required=True, choices=("editor", "approver"))
    r = sub.add_parser("revoke", help="entra como owner e revoga concessão de papel")
    r.add_argument("--grant-id", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        settings = load_settings(env)
        if not settings.database_url:
            raise ConfigError("FORGE_DATABASE_URL é obrigatória")
        if not settings.github_client_id:
            raise ConfigError("FORGE_GITHUB_CLIENT_ID é obrigatória para entrar")
        repo = open_repository(settings.database_url, settings.database_migration_url)
        flow = DeviceFlow(settings.github_client_id, transport or UrllibTransport())
        store = AuthStore(repo, verify=flow.identity)

        if args.cmd == "bootstrap":
            return _bootstrap(store, flow, args.expect_github_id, out)

        def operation(principal: Principal) -> int:
            if args.cmd == "whoami":
                roles = [r for r in ("owner", "editor", "approver") if store.has_role(principal.identity_id, r)]
                print(json.dumps({"login": principal.login, "identity": principal.identity_id, "roles": roles}),
                      file=out)
            elif args.cmd == "grant":
                store.grant_role(principal, args.github_id, args.role)
                print("Papel concedido.", file=out)
            elif args.cmd == "revoke":
                store.revoke_role(principal, args.grant_id)
                print("Papel revogado.", file=out)
            return 0

        return _with_login(store, flow, out, operation)
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
