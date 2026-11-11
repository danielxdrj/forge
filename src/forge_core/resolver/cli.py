"""CLI `resolver`: validações locais baratas, depois sessão editor, clone, motor, confirmação, PR rascunho."""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

from ..auth.cli import _with_login
from ..auth.github import DeviceFlow, DeviceFlowError, Transport, UrllibTransport
from ..auth.store import AuthStore
from ..config import load_settings
from ..draft.cursor_cli import implementer_adapter, resolve_cursor_model
from ..draft.github_gh import GhCli
from ..draft.service import ask_confirm
from ..errors import AuthenticationError, AuthorizationError, ConfigError, DraftError, ForgeError
from ..storage.sql import open_repository
from ..tasks.service import TaskService
from .gitops import GitCli
from .service import ResolverService, parse_issue_ref

QUESTION = "Publicar branch e abrir PR em rascunho no GitHub? [s/N]"


def _flag_given(argv: list[str], name: str) -> bool:
    token = f"--{name}"
    return any(a == token or a.startswith(token + "=") for a in argv)


def add_parser(sub) -> None:
    r = sub.add_parser("resolver", help="implementar issue no clone temporário e abrir PR em rascunho")
    r.add_argument("issue", nargs="?", default="", help="owner/repo#n")
    r.add_argument("--retomar", default="", help="id da tarefa Forge (recupera parâmetros; flags só sobrescrevem)")
    r.add_argument("--model", default="", help="mesmo que FORGE_CURSOR_MODEL (precedência: flag > env)")
    r.add_argument("--manter-clone", action="store_true", help="não apaga o clone temporário")
    r.add_argument("--attempts", type=int, default=0, help="teto de tentativas do motor (1-3)")


def run(argv: list[str], env: Mapping[str, str] | None = None, transport: Transport | None = None,
        provider=None, gh=None, git=None, out=None, err=None, stdin=None) -> int:
    env = os.environ if env is None else env
    out = out or sys.stdout
    err = err or sys.stderr
    stdin = sys.stdin if stdin is None else stdin
    parser = argparse.ArgumentParser(prog="forge-resolver", description="Resolver de issue (Forge).")
    sub = parser.add_subparsers(dest="cmd", required=False)
    add_parser(sub)
    # `python -m forge_core.resolver owner/repo#n` (sem subcomando)
    if argv and not argv[0].startswith("-") and argv[0] not in {"resolver", "draft", "doctor"}:
        if "#" in argv[0]:
            argv = ["resolver", *argv]
    elif not argv or argv[0] != "resolver":
        if argv and argv[0].startswith("--"):
            argv = ["resolver", *argv]
    args = parser.parse_args(argv)
    if getattr(args, "cmd", None) not in (None, "resolver"):
        return 1
    if not hasattr(args, "issue"):
        parser.parse_args(["--help"])
        return 1
    try:
        return _execute(args, argv, env, transport, provider, gh, git, out, err, stdin)
    except DeviceFlowError as exc:
        print(f"forge-tasks: falha no login ({exc.code})", file=err)
    except DraftError as exc:
        print(f"forge-tasks: {exc}", file=err)
    except (AuthenticationError, AuthorizationError, ConfigError) as exc:
        print(f"forge-tasks: {exc}", file=err)
    except ForgeError as exc:
        print(f"forge-tasks: erro ({type(exc).__name__})", file=err)
    return 1


def _execute(args, argv, env, transport, provider, gh, git, out, err, stdin) -> int:
    if not args.retomar:
        if not (args.issue or "").strip():
            raise DraftError("invalid_issue_ref")
        parse_issue_ref(args.issue)
    elif args.issue and _flag_given(list(argv), "unused-never"):
        pass
    elif args.issue:
        parse_issue_ref(args.issue)

    model = resolve_cursor_model(env, flag=args.model)
    if not args.retomar and provider is None and not model:
        raise DraftError("model_required")

    settings = load_settings(env)
    if not settings.database_url:
        raise ConfigError("FORGE_DATABASE_URL é obrigatória")
    if not settings.github_client_id:
        raise ConfigError("FORGE_GITHUB_CLIENT_ID é obrigatória para entrar")

    timeout = int(env.get("FORGE_CURSOR_TIMEOUT", "600") or 600)
    attempts = args.attempts or int(env.get("FORGE_RESOLVER_ATTEMPTS", "1") or 1)
    repo_db = open_repository(settings.database_url, settings.database_migration_url)
    flow = DeviceFlow(settings.github_client_id, transport or UrllibTransport())
    store = AuthStore(repo_db, verify=flow.identity)
    tasks = TaskService(repo_db)
    gh_cli = gh if gh is not None else GhCli(
        bin_path=env.get("FORGE_GH_BIN", "gh").strip() or "gh", env=env,
    )
    git_cli = git if git is not None else GitCli(env=env)

    def operation(principal):
        adapter = provider
        keep = bool(args.manter_clone)
        if adapter is None:
            adapter = implementer_adapter(
                model=model or None, timeout=timeout, env=env,
            )
        service = ResolverService(tasks, adapter, gh_cli, git=git_cli, attempts=attempts)
        if args.retomar:
            result = service.load_resume(
                args.retomar, principal,
                issue_ref=args.issue if args.issue else "",
                model=model if _flag_given(list(argv), "model") else "",
                keep_clone=keep if _flag_given(list(argv), "manter-clone") else None,
            )
        else:
            result = service.start(
                args.issue, principal, model=model or "", keep_clone=keep,
            )
        if result.state.phase == "pushed":
            print(f"PR {result.state.pr_url}\ntarefa {result.task_id}", file=out)
            return 0
        try:
            ok = ask_confirm(result.preview, yes=False, stdin=stdin, out=out, question=QUESTION)
        except DraftError:
            print("Publicação recusada (sem TTY). Confirme com s/N no terminal. Clone local mantido só com --manter-clone.", file=out)
            print(f"tarefa {result.task_id}", file=out)
            if not result.state.keep_clone:
                service.cleanup(result.state)
            return 0
        if not ok:
            print(f"tarefa {result.task_id}", file=out)
            if not result.state.keep_clone:
                service.cleanup(result.state)
            return 0
        published = service.confirm_and_publish(result, principal)
        print(
            f"PR {published.state.pr_url}\nbranch {published.state.branch}\ntarefa {published.task_id}",
            file=out,
        )
        return 0

    return _with_login(store, flow, out, operation)


def main() -> int:
    return run(sys.argv[1:])
