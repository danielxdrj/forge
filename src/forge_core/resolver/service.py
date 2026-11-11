"""Orquestra clone temporário, motor implementador, validação, confirmação, push e PR rascunho."""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..agents.provider import ProviderAdapter
from ..auth.store import Principal
from ..draft.github_gh import GhCli
from ..draft.service import attach_draft, parse_draft_params, write_draft_sidecar, read_draft_sidecar
from ..draft.template import branch_name, slug, validate_repo
from ..errors import DraftError
from ..logging import redact
from ..tasks.service import TaskService
from .context_pack import build_pack
from .gitops import GitCli
from .prompt import build_implementer_prompt
from .validate import assert_git_meta_unchanged, snapshot_git_meta, validate_diff

PHASES = ("none", "cloned", "implemented", "validated", "pushed")
RESOLVE_START = "\n<!-- forge-resolve "
RESOLVE_END = " -->"
DEFAULT_ATTEMPTS = 1
MAX_ATTEMPTS = 3
CLONE_PREFIX = "forge-resolver-"


@dataclass
class ResolveState:
    repo: str = ""
    issue: int | None = None
    branch: str = ""
    clone: str = ""
    phase: str = "none"
    keep_clone: bool = False
    model: str = ""
    report: str = ""
    diff_hash: str = ""
    pr_url: str = ""
    tests: str = ""


@dataclass
class ResolveResult:
    task_id: str
    state: ResolveState
    title: str = ""
    diff: str = ""
    preview: str = ""
    meta: dict = field(default_factory=dict)


def parse_issue_ref(raw: str) -> tuple[str, int]:
    text = (raw or "").strip()
    if "#" not in text:
        raise DraftError("invalid_issue_ref")
    repo, num = text.rsplit("#", 1)
    repo = validate_repo(repo)
    try:
        number = int(num)
    except ValueError as exc:
        raise DraftError("invalid_issue_ref") from exc
    if number < 1:
        raise DraftError("invalid_issue_ref")
    return repo, number


def _later(a: str, b: str) -> str:
    order = PHASES
    ia = order.index(a) if a in order else 0
    ib = order.index(b) if b in order else 0
    return order[max(ia, ib)]


def state_to_dict(state: ResolveState) -> dict:
    return {
        "repo": state.repo, "issue": state.issue, "branch": state.branch,
        "clone": state.clone, "phase": state.phase, "keep_clone": state.keep_clone,
        "model": state.model, "report": state.report, "diff_hash": state.diff_hash,
        "pr_url": state.pr_url, "tests": state.tests,
    }


def state_from_dict(data: dict) -> ResolveState:
    return ResolveState(
        repo=str(data.get("repo") or ""),
        issue=data.get("issue"),
        branch=str(data.get("branch") or ""),
        clone=str(data.get("clone") or ""),
        phase=str(data.get("phase") or "none"),
        keep_clone=bool(data.get("keep_clone")),
        model=str(data.get("model") or ""),
        report=str(data.get("report") or ""),
        diff_hash=str(data.get("diff_hash") or ""),
        pr_url=str(data.get("pr_url") or ""),
        tests=str(data.get("tests") or ""),
    )


def checkpoint_path(clone: Path) -> Path:
    return clone.parent / f"{clone.name}.forge-resolve.json"


def draft_params_path(clone: Path) -> Path:
    return clone.parent / f"{clone.name}.md"


def write_checkpoint(state: ResolveState) -> None:
    if not state.clone:
        return
    path = checkpoint_path(Path(state.clone))
    path.write_text(json.dumps(state_to_dict(state), ensure_ascii=False), encoding="utf-8")


def read_checkpoint(clone: Path) -> ResolveState | None:
    path = checkpoint_path(clone)
    if not path.is_file():
        return None
    try:
        return state_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError):
        raise DraftError("checkpoint_invalid")


def tests_line(report: str) -> str:
    text = report or ""
    low = text.lower()
    if "testes não rodados" in low or "testes nao rodados" in low:
        return "testes não rodados"
    if "test" in low:
        return redact(text)[:500]
    return "testes não rodados"


class ResolverService:
    def __init__(self, tasks: TaskService, provider: ProviderAdapter, gh: GhCli,
                 git: GitCli | None = None, attempts: int = DEFAULT_ATTEMPTS):
        self.tasks = tasks
        self.provider = provider
        self.gh = gh
        self.git = git or GitCli()
        self.attempts = min(max(int(attempts), 1), MAX_ATTEMPTS)

    def start(self, issue_ref: str, principal: Principal, *, model: str = "",
              keep_clone: bool = False) -> ResolveResult:
        repo, number = parse_issue_ref(issue_ref)
        self.tasks._auth.require(principal, "editor")
        task = self.tasks.create_task(
            f"resolver {repo}#{number}", principal,
            objective="Implementar a issue no clone temporário e abrir PR em rascunho.",
            context=issue_ref,
            assignee_kind="person",
            assignee_id=principal.identity_id,
        )
        state = ResolveState(repo=repo, issue=number, keep_clone=keep_clone, model=model)
        result = ResolveResult(task.id, state, meta={"issue_ref": issue_ref, "model": model})
        self._save_params(result, principal)
        return self._run_from(result, principal)

    def load_resume(self, task_id: str, principal: Principal, *, issue_ref: str = "",
                    model: str = "", keep_clone: bool | None = None) -> ResolveResult:
        self.tasks._auth.require(principal, "editor")
        task = self.tasks.get_task(task_id)
        if task is None:
            raise DraftError("task_missing")
        saved = parse_draft_params(task.context)
        sidecar = {}
        output = saved.get("output")
        if output:
            sidecar = read_draft_sidecar(Path(output))
        merged = {**sidecar, **saved}
        ref = issue_ref or merged.get("issue_ref") or task.context.split(RESOLVE_START, 1)[0].strip()
        if "#" in ref:
            repo, number = parse_issue_ref(ref.split(RESOLVE_START)[0].strip() or ref)
        else:
            raise DraftError("invalid_issue_ref")
        clone = str(merged.get("clone") or "")
        state = ResolveState(repo=repo, issue=number, clone=clone)
        if clone and Path(clone).is_dir():
            ck = read_checkpoint(Path(clone))
            if ck:
                state = ck
        elif clone:
            state.phase = "none"
            state.clone = ""
        if issue_ref:
            repo, number = parse_issue_ref(issue_ref)
            if state.issue and state.issue != number:
                raise DraftError("repo_mismatch")
            state.repo, state.issue = repo, number
        if model:
            state.model = model
        elif merged.get("model"):
            state.model = str(merged.get("model"))
        if keep_clone is not None:
            state.keep_clone = keep_clone
        result = ResolveResult(
            task.id, state, title=task.title,
            meta={"issue_ref": f"{state.repo}#{state.issue}", "model": state.model},
        )
        return self._run_from(result, principal)

    def _run_from(self, result: ResolveResult, principal: Principal) -> ResolveResult:
        state = result.state
        created_clone = False
        try:
            if state.phase == "none":
                self._clone(state)
                created_clone = True
                state.phase = "cloned"
                write_checkpoint(state)
                self._save_params(result, principal)
            if state.phase == "cloned":
                self._implement(state)
                state.phase = "implemented"
                write_checkpoint(state)
                self._save_params(result, principal)
            if state.phase == "implemented":
                result.diff = self._validate(state)
                state.phase = "validated"
                write_checkpoint(state)
                self._save_params(result, principal)
            result.preview = self._preview(state, result.diff)
            result.title = result.title or f"{state.repo}#{state.issue}"
            return result
        except Exception:
            if created_clone and not state.keep_clone and state.phase == "none":
                self.cleanup(state)
            raise

    def confirm_and_publish(self, result: ResolveResult, principal: Principal) -> ResolveResult:
        self.tasks._auth.require(principal, "editor")
        state = result.state
        if state.phase != "validated":
            raise DraftError("phase_invalid")
        if not result.diff:
            result.diff = self.git.diff(state.clone)
        self._ensure_commit(state, result.diff)
        self.git.push(state.clone, state.branch)
        if any("push" in " ".join(c) and "gh" == c[0] for c in self.gh.calls):
            raise DraftError("unsafe_flags")
        title = result.title or f"fix: {state.repo}#{state.issue}"
        if not title.lower().startswith(("feat", "fix", "docs", "test", "chore", "refactor", "perf", "build", "ci", "style", "revert")):
            title = f"fix: resolve #{state.issue}"
        body = f"Closes #{state.issue}\n\n{redact(state.report)[:1000]}"
        url = self.gh.create_draft_pr(state.repo, title, body, state.branch)
        if "pr merge" in " ".join(" ".join(c) for c in self.gh.calls):
            raise DraftError("unsafe_flags")
        state.pr_url = url
        state.phase = "pushed"
        write_checkpoint(state)
        self._audit(principal, state)
        self._save_params(result, principal)
        if not state.keep_clone:
            self.cleanup(state)
        return result

    def cleanup(self, state: ResolveState) -> None:
        if not state.clone or state.keep_clone:
            return
        clone = Path(state.clone)
        shutil.rmtree(clone, ignore_errors=True)
        for extra in (checkpoint_path(clone), draft_params_path(clone).with_name(
                draft_params_path(clone).name + ".forge-draft.json")):
            extra.unlink(missing_ok=True)

    def _clone(self, state: ResolveState) -> None:
        dest = tempfile.mkdtemp(prefix=CLONE_PREFIX)
        state.clone = dest
        self.gh.clone_repo(state.repo, dest)
        detail = self.gh.view_issue_detail(state.issue, state.repo)
        title = str(detail.get("title") or f"issue-{state.issue}")
        linked = self.gh.list_issue_branches(state.repo, state.issue)
        branch = linked[0] if linked else branch_name(state.issue, title, "")
        if not linked:
            branch = f"{state.issue}-{slug(title)}"
        state.branch = branch
        self.git.checkout_or_create(dest, branch, existing=bool(linked))

    def _implement(self, state: ResolveState) -> None:
        if hasattr(self.provider, "workspace"):
            self.provider.workspace = state.clone
        detail = self.gh.view_issue_detail(state.issue, state.repo)
        tracked = []
        try:
            tracked = self.git.ls_files(state.clone)
        except DraftError:
            tracked = []
        pack = build_pack(issue=detail, root=Path(state.clone), tracked=tracked)
        prompt = build_implementer_prompt(pack)
        if "GH_TOKEN" in prompt or "FORGE_" in prompt:
            raise DraftError("secret_in_prompt")
        last_err = None
        text = ""
        for _ in range(self.attempts):
            try:
                text = self.provider.complete(prompt).text
                last_err = None
                break
            except DraftError as exc:
                last_err = exc
        if last_err:
            raise last_err
        state.report = redact(text)
        state.tests = tests_line(state.report)

    def _validate(self, state: ResolveState) -> str:
        root = Path(state.clone)
        before = snapshot_git_meta(root)
        diff = self.git.diff(state.clone)
        info = validate_diff(diff, root)
        assert_git_meta_unchanged(root, before)
        state.diff_hash = info["hash"]
        self._ensure_commit(state, diff)
        return diff

    def _ensure_commit(self, state: ResolveState, diff: str) -> None:
        if self.git.status(state.clone).strip():
            self.git.add_all(state.clone)
            msg = f"fix: resolve #{state.issue}"
            self.git.commit(state.clone, msg)

    def _preview(self, state: ResolveState, diff: str) -> str:
        return "\n".join([
            "=== RESOLVER ===",
            f"repo: {state.repo}#{state.issue}",
            f"branch: {state.branch}",
            f"clone: {state.clone}",
            f"modelo: {state.model or '(padrão da CLI)'}",
            f"hash: {state.diff_hash}",
            f"testes: {state.tests or 'testes não rodados'}",
            "=== RELATORIO ===",
            redact(state.report)[:2000] or "(vazio)",
            "=== DIFF ===",
            (diff or "")[:4000],
            "Mutações se confirmado: git push da branch; gh pr create --draft com Closes #n. Sem merge.",
        ])

    def _save_params(self, result: ResolveResult, principal: Principal) -> None:
        task = self.tasks.get_task(result.task_id)
        if task is None:
            raise DraftError("task_missing")
        params = {
            "task_id": result.task_id,
            "issue_ref": f"{result.state.repo}#{result.state.issue}",
            "clone": result.state.clone,
            "model": result.state.model,
            "keep_clone": result.state.keep_clone,
            "phase": result.state.phase,
            "output": str(draft_params_path(Path(result.state.clone))) if result.state.clone else "",
        }
        result.meta = {**result.meta, **params}
        if result.state.clone:
            write_draft_sidecar(draft_params_path(Path(result.state.clone)), params)
            write_checkpoint(result.state)
        context = attach_draft(f"{params['issue_ref']}", params)
        self.tasks.update_task(result.task_id, principal, task.version, context=context)

    def _audit(self, principal: Principal, state: ResolveState) -> None:
        self.tasks._repo.record_audit(
            principal.identity_id,
            "resolver.approve",
            f"{state.repo}#{state.issue}",
            f"hash={state.diff_hash} model={state.model or '-'} pr=draft",
        )
