"""Orquestra rascunho local, tarefa Forge e (depois da confirmação) o gh do usuário.

Rede e banco não são uma transação. Checkpoint em arquivo ao lado do markdown
recupera o vínculo se a gravação local falhar depois da issue.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..agents.provider import ProviderAdapter
from ..auth.store import Principal
from ..errors import DraftError
from ..logging import redact
from ..tasks.service import TaskService
from .cursor_cli import build_prompt
from .github_gh import (
    GhCli, RemoteState, current_iteration_id, find_field, match_option,
)
from .template import (
    ASSIGNEE, PENDING, PROJECT_NUMBER, PROJECT_OWNER, PROJECT_TITLE,
    branch_name, parse_model_json, render, required_pending, validate_repo,
)

REMOTE_START = "\n<!-- forge-remote "
REMOTE_END = " -->"


@dataclass
class DraftResult:
    task_id: str
    title: str
    body: str
    path: str
    remote: RemoteState
    published: bool


def sidecar_path(output: Path) -> Path:
    return output.with_name(output.name + ".forge-remote.json")


def parse_remote(context: str) -> RemoteState:
    if REMOTE_START not in context:
        return RemoteState()
    raw = context.split(REMOTE_START, 1)[1].split(REMOTE_END, 1)[0]
    try:
        data = json.loads(raw)
        return _state_from_dict(data)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return RemoteState()


def _state_from_dict(data: dict) -> RemoteState:
    return RemoteState(
        issue=data.get("issue"), url=data.get("url"),
        branch=data.get("branch"), item_id=data.get("item_id"),
        phase=data.get("phase") or "none", repo=data.get("repo"),
    )


def attach_remote(context: str, remote: RemoteState) -> str:
    base = context.split(REMOTE_START, 1)[0].rstrip()
    payload = json.dumps(_state_to_dict(remote), ensure_ascii=False)
    return f"{base}{REMOTE_START}{payload}{REMOTE_END}\n"


def _state_to_dict(remote: RemoteState) -> dict:
    return {
        "issue": remote.issue, "url": remote.url, "branch": remote.branch,
        "item_id": remote.item_id, "phase": remote.phase, "repo": remote.repo,
    }


def write_checkpoint(output: Path, remote: RemoteState) -> None:
    sidecar_path(output).write_text(
        json.dumps(_state_to_dict(remote), ensure_ascii=False), encoding="utf-8")


def read_checkpoint(output: Path) -> RemoteState | None:
    path = sidecar_path(output)
    if not path.is_file():
        return None
    try:
        return _state_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, OSError):
        raise DraftError("checkpoint_invalid")


def merge_remote(a: RemoteState, b: RemoteState | None) -> RemoteState:
    if b is None:
        return a
    if a.url and b.url and a.url.rstrip("/") != b.url.rstrip("/"):
        raise DraftError("remote_mismatch")
    return RemoteState(
        issue=a.issue or b.issue,
        url=a.url or b.url,
        branch=a.branch or b.branch,
        item_id=a.item_id or b.item_id,
        phase=_later_phase(a.phase, b.phase),
        repo=a.repo or b.repo,
    )


def _later_phase(x: str, y: str) -> str:
    order = ("none", "issue", "board", "done")
    return order[max(order.index(x if x in order else "none"), order.index(y if y in order else "none"))]


def write_exclusive(path: Path, text: str) -> None:
    try:
        with path.open("x", encoding="utf-8") as fh:
            fh.write(text)
    except FileExistsError as exc:
        raise DraftError("file_exists") from exc


class DraftService:
    def __init__(self, tasks: TaskService, provider: ProviderAdapter, gh: GhCli | None = None,
                 today: date | None = None):
        self.tasks = tasks
        self.provider = provider
        self.gh = gh
        self.today = today or date.today()

    def generate(self, context: str, repo: str, principal: Principal, output: Path,
                 meta: dict, branch_prefix: str = "") -> DraftResult:
        repo = validate_repo(repo)
        self.tasks._auth.require(principal, "editor")
        context = redact(context.strip())
        if not context:
            raise DraftError("empty_context")
        prompt = build_prompt(context)
        if "FORGE_" in prompt or "GH_TOKEN" in prompt or "GITHUB_TOKEN" in prompt:
            raise DraftError("secret_in_prompt")
        try:
            response = self.provider.complete(prompt)
        except DraftError:
            raise
        except Exception as exc:
            raise DraftError("provider_error") from exc
        data = parse_model_json(response.text)
        body = render(data)
        write_exclusive(output, body)
        task = self.tasks.create_task(
            data["title"], principal,
            objective=data["objetivo"],
            context=context,
            acceptance_criteria="\n".join(f"- {c}" for c in data["criterios"]),
            assignee_kind="person",
            assignee_id=ASSIGNEE,
        )
        return DraftResult(task.id, data["title"], body, str(output), RemoteState(repo=repo), False)

    def load_resume(self, task_id: str, output: Path, principal: Principal, repo: str) -> DraftResult:
        self.tasks._auth.require(principal, "editor")
        repo = validate_repo(repo)
        task = self.tasks.get_task(task_id)
        if task is None:
            raise DraftError("task_missing")
        if not output.is_file():
            raise DraftError("file_missing")
        body = output.read_text(encoding="utf-8")
        remote = merge_remote(parse_remote(task.context), read_checkpoint(output))
        remote.repo = remote.repo or repo
        return DraftResult(task.id, task.title, body, str(output), remote, remote.phase == "done")

    def preview_text(self, result: DraftResult, repo: str, meta: dict, branch_prefix: str) -> str:
        pending = required_pending(parse_model_json_from_body(result.body), meta)
        return "\n".join([
            "=== ISSUE ===",
            result.body.rstrip(),
            "=== DESTINO ===",
            f"repo: {repo}",
            f"assignee: {ASSIGNEE}",
            f"board: {PROJECT_OWNER}/{PROJECT_TITLE} projects/{PROJECT_NUMBER}",
            f"sprint: {meta.get('sprint') or 'semana atual (schema do board)'}",
            f"tipo: {meta.get('tipo') or PENDING}",
            f"prioridade: {meta.get('prioridade') or PENDING}",
            f"size: {meta.get('size') or PENDING}",
            f"escopo (só board): {meta.get('escopo') or '(campo ausente = não preenchido)'}",
            f"branch prevista: {branch_prefix or ''}N-slug",
            f"arquivo: {result.path}",
            f"tarefa: {result.task_id}",
            f"fase remota: {result.remote.phase}",
            f"pendencias: {', '.join(pending) if pending else '(nenhuma)'}",
            "Mutações se confirmado: gh issue create (só se ainda não houver issue); "
            "project item-add; item-edit; issue develop. Sem apagar issue.",
        ])

    def publish(self, result: DraftResult, repo: str, principal: Principal, meta: dict,
                branch_prefix: str = "") -> DraftResult:
        if self.gh is None:
            raise DraftError("gh_missing")
        data = parse_model_json_from_body(result.body)
        pending = required_pending(data, meta)
        if pending:
            raise DraftError("pending_required", ",".join(pending))
        self.tasks._auth.require(principal, "editor")
        task = self.tasks.get_task(result.task_id)
        if task is None:
            raise DraftError("task_missing")
        output = Path(result.path)
        remote = merge_remote(parse_remote(task.context), read_checkpoint(output))
        remote.repo = remote.repo or repo
        gh = self.gh
        remote = self._reconcile(gh, remote, repo, result.title)
        if remote.phase == "none":
            gh.preflight()
            fields = gh.list_fields()
            self._resolve_board(fields, meta)
            ref = gh.create_issue(repo, result.title, result.path, ASSIGNEE)
            remote = RemoteState(issue=ref.number, url=ref.url, phase="issue", repo=repo)
            write_checkpoint(output, remote)
            self._save_remote(result.task_id, principal, remote)
            task = self.tasks.get_task(result.task_id)
        if remote.phase == "issue":
            write_checkpoint(output, remote)
            gh.preflight()
            fields = gh.list_fields()
            ids = self._resolve_board(fields, meta)
            item_id = remote.item_id or gh.add_to_project(remote.url)
            remote.item_id = item_id
            sprint_field, sprint_opt = ids["sprint"]
            tipo_field, tipo_opt = ids["tipo"]
            pri_field, pri_opt = ids["prioridade"]
            size_field, size_opt = ids["size"]
            gh.edit_iteration(item_id, sprint_field, sprint_opt)
            gh.edit_select(item_id, tipo_field, tipo_opt)
            gh.edit_select(item_id, pri_field, pri_opt)
            gh.edit_select(item_id, size_field, size_opt)
            if ids.get("escopo"):
                ef, eo = ids["escopo"]
                gh.edit_select(item_id, ef, eo)
            remote.phase = "board"
            write_checkpoint(output, remote)
            self._save_remote(result.task_id, principal, remote)
            task = self.tasks.get_task(result.task_id)
        if remote.phase == "board":
            name = branch_name(remote.issue, result.title, branch_prefix)
            remote.branch = gh.develop(repo, remote.issue, name)
            remote.phase = "done"
            write_checkpoint(output, remote)
            self._save_remote(result.task_id, principal, remote)
        result.remote = remote
        result.published = remote.phase == "done"
        return result

    def _reconcile(self, gh: GhCli, remote: RemoteState, repo: str, title: str) -> RemoteState:
        if not remote.url and remote.phase == "none":
            return remote
        if not remote.url:
            raise DraftError("remote_mismatch")
        viewed = gh.view_issue(remote.url, repo)
        if remote.issue is not None and viewed.number != remote.issue:
            raise DraftError("remote_mismatch")
        if viewed.title and viewed.title != title:
            raise DraftError("remote_mismatch")
        remote.issue = viewed.number
        remote.url = viewed.url
        if remote.phase == "none":
            remote.phase = "issue"
        return remote

    def _save_remote(self, task_id: str, principal: Principal, remote: RemoteState) -> None:
        task = self.tasks.get_task(task_id)
        if task is None:
            raise DraftError("task_missing")
        self.tasks.update_task(
            task_id, principal, task.version,
            context=attach_remote(task.context, remote),
        )

    def _resolve_board(self, fields: list[dict], meta: dict) -> dict:
        out = {}
        sprint = find_field(fields, "sprint")
        out["sprint"] = (sprint["id"], current_iteration_id(sprint, self.today, meta.get("sprint")))
        for key in ("tipo", "prioridade", "size"):
            field = find_field(fields, key)
            out[key] = (field["id"], match_option(field, meta[key]))
        try:
            escopo = find_field(fields, "escopo")
        except DraftError:
            escopo = None
        if escopo and (meta.get("escopo") or "").strip():
            out["escopo"] = (escopo["id"], match_option(escopo, meta["escopo"]))
        return out


def parse_model_json_from_body(body: str) -> dict:
    """Reconstrói o dict a partir do markdown já validado (não chama o LLM)."""
    lines = body.strip().splitlines()
    if not lines:
        raise DraftError("invalid_draft")
    title = lines[0]

    def after(header: str) -> list[str]:
        try:
            i = lines.index(header)
        except ValueError as exc:
            raise DraftError("invalid_draft") from exc
        acc = []
        for line in lines[i + 1:]:
            if line in ("Solicitado Por", "Objetivo", "Contexto",
                        "Foram reportados os seguintes problemas:",
                        "Situação Atual", "Comportamento Esperado",
                        "Critérios de Aceite", "Observações") and line != header:
                break
            acc.append(line)
        return acc

    def bullets(block):
        return [ln[2:].strip() for ln in block if ln.startswith("- ")] or [PENDING]

    problemas_block = after("Foram reportados os seguintes problemas:")
    novos = ""
    items = []
    for ln in problemas_block:
        if ln.startswith("- "):
            items.append(ln[2:].strip())
        elif ln.strip():
            novos = ln.strip()
    return {
        "title": title,
        "solicitado_por": bullets(after("Solicitado Por"))[0],
        "objetivo": "\n".join(after("Objetivo")).strip() or PENDING,
        "contexto": "\n".join(after("Contexto")).strip() or PENDING,
        "problemas": items or [PENDING],
        "novos_problemas": novos,
        "situacao_atual": "\n".join(after("Situação Atual")).strip() or PENDING,
        "comportamento_esperado": bullets(after("Comportamento Esperado")),
        "criterios": bullets(after("Critérios de Aceite")),
        "observacoes": after("Observações") or [PENDING],
    }


def ask_confirm(text: str, *, yes: bool, stdin, out) -> bool:
    print(text, file=out)
    print("Criar issue/board/branch no GitHub? [s/N]", file=out)
    if yes:
        return True
    if stdin is None or not hasattr(stdin, "isatty") or not stdin.isatty():
        raise DraftError("confirmation_required")
    line = stdin.readline()
    return line.strip().lower() in {"s", "sim", "y", "yes"}
