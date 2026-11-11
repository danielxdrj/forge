"""CLI forge-tasks draft: gera rascunho e, se confirmado, publica com o gh do usuário."""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from ..auth.cli import _with_login
from ..auth.github import DeviceFlow, DeviceFlowError, Transport, UrllibTransport
from ..auth.store import AuthStore
from ..config import load_settings
from ..errors import AuthenticationError, AuthorizationError, ConfigError, DraftError, ForgeError
from ..storage.sql import open_repository
from ..tasks.service import TaskService
from .context import resolve_source
from .cursor_cli import CursorCliAdapter, diagnose_cursor_cli
from .github_gh import GhCli
from .service import DraftService, ask_confirm
from .template import validate_repo


def run(argv: list[str], env: Mapping[str, str] | None = None, transport: Transport | None = None,
        provider=None, gh=None, out=None, err=None, stdin=None) -> int:
    env = os.environ if env is None else env
    out = out or sys.stdout
    err = err or sys.stderr
    stdin = sys.stdin if stdin is None else stdin
    parser = argparse.ArgumentParser(prog="forge-tasks", description="Rascunho de issue (Forge).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="diagnóstico do adaptador Cursor CLI (sem valores de segredo)")
    d = sub.add_parser("draft", help="gerar rascunho e opcionalmente publicar com gh local")
    d.add_argument("context", nargs="?", help="alias do --contexto")
    d.add_argument("--contexto", default="", help="contexto em texto livre")
    d.add_argument("--arquivo", default="", help="arquivo UTF-8 com o contexto, ou - para stdin")
    d.add_argument("--retomar", default="", help="id da tarefa Forge já gerada (não chama o LLM)")
    d.add_argument("--repo", required=True, help="owner/repo alvo")
    d.add_argument("--output", default="issue-draft.md", help="markdown de saída (não sobrescreve)")
    d.add_argument("--yes", action="store_true", help="pula só a confirmação s/N")
    d.add_argument("--sprint", default="", help="título da iteração no board (senão a semana atual do schema)")
    d.add_argument("--tipo", default="")
    d.add_argument("--prioridade", default="")
    d.add_argument("--size", default="")
    d.add_argument("--escopo", default="", help="só campo de board, nunca seção do corpo")
    d.add_argument("--branch-prefix", default="", help="prefixo já usado no cadastro (ADR-012)")
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        try:
            return diagnose_cursor_cli(env, out=out)
        except DraftError as exc:
            print(f"forge-tasks: {exc}", file=err)
            return 1
        except ForgeError as exc:
            print(f"forge-tasks: erro ({type(exc).__name__})", file=err)
            return 1
    if args.cmd != "draft":
        return 1
    try:
        settings = load_settings(env)
        if not settings.database_url:
            raise ConfigError("FORGE_DATABASE_URL é obrigatória")
        if not settings.github_client_id:
            raise ConfigError("FORGE_GITHUB_CLIENT_ID é obrigatória para entrar")
        validate_repo(args.repo)
        model = env.get("FORGE_CURSOR_MODEL", "").strip()
        if not args.retomar and provider is None and not model:
            raise DraftError("model_required")

        def _stdin() -> bytes:
            return stdin.buffer.read() if hasattr(stdin, "buffer") else stdin.read().encode("utf-8")

        context = ""
        if not args.retomar:
            context = resolve_source(
                contexto=args.contexto, arquivo=args.arquivo, positional=args.context,
                stdin_read=_stdin,
            ).load()
        elif args.contexto or args.arquivo or args.context:
            raise DraftError("context_ambiguous")
        repo_db = open_repository(settings.database_url, settings.database_migration_url)
        flow = DeviceFlow(settings.github_client_id, transport or UrllibTransport())
        store = AuthStore(repo_db, verify=flow.identity)
        tasks = TaskService(repo_db)
        adapter = provider or CursorCliAdapter(
            model=model or None,
            timeout=int(env.get("FORGE_CURSOR_TIMEOUT", "120") or 120),
            env=env,
        )
        gh_cli = gh if gh is not None else GhCli(
            bin_path=env.get("FORGE_GH_BIN", "gh").strip() or "gh", env=env,
        )
        service = DraftService(tasks, adapter, gh_cli)

        def operation(principal):
            meta = {
                "sprint": args.sprint, "tipo": args.tipo, "prioridade": args.prioridade,
                "size": args.size, "escopo": args.escopo,
            }
            out_path = Path(args.output)
            if args.retomar:
                result = service.load_resume(args.retomar, out_path, principal, args.repo)
            else:
                result = service.generate(
                    context, args.repo, principal, out_path, meta, args.branch_prefix,
                )
            preview = service.preview_text(result, args.repo, meta, args.branch_prefix)
            try:
                ok = ask_confirm(preview, yes=args.yes, stdin=stdin, out=out)
            except DraftError:
                print("Publicação recusada (sem --yes e sem TTY). Rascunho local mantido.", file=out)
                print(f"tarefa {result.task_id}", file=out)
                return 0
            if not ok:
                print("Publicação cancelada. Rascunho local mantido.", file=out)
                print(f"tarefa {result.task_id}", file=out)
                return 0
            published = service.publish(result, args.repo, principal, meta, args.branch_prefix)
            print(
                f"Issue {published.remote.issue} {published.remote.url}\n"
                f"branch {published.remote.branch}\ntarefa {published.task_id}",
                file=out,
            )
            return 0

        return _with_login(store, flow, out, operation)
    except DeviceFlowError as exc:
        print(f"forge-tasks: falha no login ({exc.code})", file=err)
    except DraftError as exc:
        print(f"forge-tasks: {exc}", file=err)
        if exc.code == "project_scope":
            print("forge-tasks: rode gh auth refresh -s project (não executado por este comando)", file=err)
    except (AuthenticationError, AuthorizationError, ConfigError) as exc:
        print(f"forge-tasks: {exc}", file=err)
    except ForgeError as exc:
        print(f"forge-tasks: erro ({type(exc).__name__})", file=err)
    return 1


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
