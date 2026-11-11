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
from .cursor_cli import CursorCliAdapter, diagnose_cursor_cli, resolve_cursor_model
from .github_gh import GhCli
from .service import DraftService, ask_confirm, read_draft_sidecar
from .template import validate_repo


def _flag_given(argv: list[str], name: str) -> bool:
    token = f"--{name}"
    return any(a == token or a.startswith(token + "=") for a in argv)


def run(argv: list[str], env: Mapping[str, str] | None = None, transport: Transport | None = None,
        provider=None, gh=None, git=None, out=None, err=None, stdin=None) -> int:
    env = os.environ if env is None else env
    out = out or sys.stdout
    err = err or sys.stderr
    stdin = sys.stdin if stdin is None else stdin
    parser = argparse.ArgumentParser(prog="forge-tasks", description="Rascunho de issue (Forge).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    doc = sub.add_parser("doctor", help="diagnóstico do adaptador Cursor CLI (sem valores de segredo)")
    doc.add_argument("--model", default="", help="mesmo que FORGE_CURSOR_MODEL (precedência: flag > env)")
    d = sub.add_parser("draft", help="gerar rascunho e opcionalmente publicar com gh local")
    d.add_argument("context", nargs="?", help="alias do --contexto")
    d.add_argument("--contexto", default="", help="contexto em texto livre")
    d.add_argument("--arquivo", default="", help="arquivo UTF-8 com o contexto, ou - para stdin")
    d.add_argument("--retomar", default="", help="id da tarefa Forge já gerada (não chama o LLM)")
    d.add_argument("--repo", default="", help="owner/repo alvo (obrigatório na geração; no --retomar vem do rascunho)")
    d.add_argument("--output", default=None, help="markdown de saída (não sobrescreve; no --retomar vem do rascunho)")
    d.add_argument("--yes", action="store_true", help="pula só a confirmação s/N")
    d.add_argument("--sprint", default="")
    d.add_argument("--tipo", default="")
    d.add_argument("--prioridade", default="")
    d.add_argument("--size", default="")
    d.add_argument("--escopo", default="", help="só campo de board, nunca seção do corpo")
    d.add_argument("--branch-prefix", default="", help="prefixo já usado no cadastro (ADR-012)")
    d.add_argument("--model", default="", help="mesmo que FORGE_CURSOR_MODEL (precedência: flag > env)")
    from ..resolver import cli as resolver_cli
    resolver_cli.add_parser(sub)
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        try:
            return diagnose_cursor_cli(env, out=out, model_flag=args.model)
        except DraftError as exc:
            print(f"forge-tasks: {exc}", file=err)
            return 1
        except ForgeError as exc:
            print(f"forge-tasks: erro ({type(exc).__name__})", file=err)
            return 1
    if args.cmd == "resolver":
        try:
            return resolver_cli._execute(args, argv, env, transport, provider, gh, git, out, err, stdin)
        except DeviceFlowError as exc:
            print(f"forge-tasks: falha no login ({exc.code})", file=err)
        except DraftError as exc:
            print(f"forge-tasks: {exc}", file=err)
        except (AuthenticationError, AuthorizationError, ConfigError) as exc:
            print(f"forge-tasks: {exc}", file=err)
        except ForgeError as exc:
            print(f"forge-tasks: erro ({type(exc).__name__})", file=err)
        return 1
    if args.cmd != "draft":
        return 1
    try:
        out_path = Path(args.output) if args.output else Path("issue-draft.md")
        if not args.retomar:
            if out_path.is_file():
                rec = read_draft_sidecar(out_path)
                tid = str(rec.get("task_id") or "").strip()
                hint = f"use --retomar {tid}" if tid else ""
                raise DraftError("file_exists", hint)
            if not (args.repo or "").strip():
                raise DraftError("missing_repo")
            validate_repo(args.repo)
        elif _flag_given(argv, "repo") and args.repo:
            validate_repo(args.repo)

        settings = load_settings(env)
        if not settings.database_url:
            raise ConfigError("FORGE_DATABASE_URL é obrigatória")
        if not settings.github_client_id:
            raise ConfigError("FORGE_GITHUB_CLIENT_ID é obrigatória para entrar")
        model = resolve_cursor_model(env, flag=args.model)
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
            meta_flags = {
                "sprint": args.sprint, "tipo": args.tipo, "prioridade": args.prioridade,
                "size": args.size, "escopo": args.escopo,
            }
            if args.retomar:
                result = service.load_resume(
                    args.retomar,
                    Path(args.output) if args.output else None,
                    principal,
                    args.repo if _flag_given(argv, "repo") else "",
                )
                saved = result.meta or {}
                meta = {
                    key: (meta_flags[key] if _flag_given(argv, key) else saved.get(key) or "")
                    for key in ("sprint", "tipo", "prioridade", "size", "escopo")
                }
                repo = args.repo if _flag_given(argv, "repo") else result.remote.repo
                prefix = (
                    args.branch_prefix if _flag_given(argv, "branch-prefix") else result.branch_prefix
                )
            else:
                result = service.generate(
                    context, args.repo, principal, out_path, meta_flags, args.branch_prefix,
                )
                meta = meta_flags
                repo = args.repo
                prefix = args.branch_prefix
            preview = service.preview_text(result, repo, meta, prefix)
            try:
                ok = ask_confirm(preview, yes=args.yes, stdin=stdin, out=out)
            except DraftError:
                print("Publicação recusada (sem --yes e sem TTY). Rascunho local mantido.", file=out)
                print(f"tarefa {result.task_id}", file=out)
                return 0
            if not ok:
                print(f"tarefa {result.task_id}", file=out)
                return 0
            published = service.publish(result, repo, principal, meta, prefix)
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
