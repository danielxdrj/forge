"""Porta do GitHub CLI local. Sessão nativa do gh (keyring). Sem GH_TOKEN no env."""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

from ..errors import DraftError
from .envfilter import GH_ENV_ALLOW, filter_env
from .template import PROJECT_NUMBER, PROJECT_OWNER

Runner = Callable[..., subprocess.CompletedProcess]
MAX_OUTPUT = 256 * 1024
DEFAULT_TIMEOUT = 60

FIELD_ALIASES = {
    "sprint": ("sprint", "sprint semana", "iteration", "iteração"),
    "tipo": ("tipo", "type"),
    "prioridade": ("prioridade", "priority"),
    "size": ("size", "tamanho"),
    "escopo": ("escopo", "scope"),
}


@dataclass
class IssueRef:
    number: int
    url: str


@dataclass
class RemoteState:
    issue: int | None = None
    url: str | None = None
    branch: str | None = None
    item_id: str | None = None
    phase: str = "none"


class GhCli:
    def __init__(self, *, bin_path: str = "gh", env: Mapping[str, str] | None = None,
                 runner: Runner | None = None, timeout: int = DEFAULT_TIMEOUT,
                 today: date | None = None):
        self.bin = bin_path
        self._env = env
        self._runner = runner
        self.timeout = timeout
        self.today = today or date.today()
        self.calls: list[list[str]] = []
        self.project_id: str | None = None

    def _env_os(self) -> dict[str, str]:
        return filter_env(self._env or os.environ, GH_ENV_ALLOW)

    def _run(self, args: list[str], *, cwd: str | None = None) -> str:
        argv = [self.bin, *args]
        self.calls.append(argv)
        run = self._runner or subprocess.run
        try:
            proc = run(
                argv, cwd=cwd, env=self._env_os(), capture_output=True, check=False,
                shell=False, timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise DraftError("gh_missing") from exc
        except subprocess.TimeoutExpired as exc:
            raise DraftError("timeout") from exc
        raw = proc.stdout or b""
        if len(raw) > MAX_OUTPUT:
            raise DraftError("output_too_large")
        text = raw.decode("utf-8", "replace")
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").lower()
            if "project" in err and ("scope" in err or "403" in err or "resource not accessible" in err):
                raise DraftError("project_scope", "gh auth refresh -s project")
            raise DraftError("gh_error")
        return text

    def preflight(self) -> None:
        status = self._run(["auth", "status"])
        low = status.lower()
        if "not logged" in low or "you are not logged" in low:
            raise DraftError("gh_not_logged")
        if "project" not in low:
            # gh auth status lista scopes; ausência de project impede o board
            raise DraftError("project_scope", "gh auth refresh -s project")
        view = self._run([
            "project", "view", str(PROJECT_NUMBER), "--owner", PROJECT_OWNER, "--format", "json",
        ])
        data = _json(view)
        self.project_id = data.get("id")
        if not self.project_id:
            raise DraftError("project_schema")

    def create_issue(self, repo: str, title: str, body_path: str, assignee: str) -> IssueRef:
        text = self._run([
            "issue", "create", "--repo", repo, "--title", title, "--body-file", body_path,
            "--assignee", assignee, "--json", "number,url",
        ])
        data = _json(text)
        try:
            return IssueRef(int(data["number"]), str(data["url"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise DraftError("gh_error") from exc

    def add_to_project(self, url: str) -> str:
        text = self._run([
            "project", "item-add", str(PROJECT_NUMBER), "--owner", PROJECT_OWNER,
            "--url", url, "--format", "json",
        ])
        data = _json(text)
        item_id = data.get("id")
        if not item_id:
            raise DraftError("gh_error")
        return str(item_id)

    def list_fields(self) -> list[dict]:
        text = self._run([
            "project", "field-list", str(PROJECT_NUMBER), "--owner", PROJECT_OWNER,
            "--format", "json", "--limit", "100",
        ])
        data = _json(text)
        fields = data.get("fields", data if isinstance(data, list) else [])
        if not isinstance(fields, list):
            raise DraftError("project_schema")
        return fields

    def edit_select(self, item_id: str, field_id: str, option_id: str) -> None:
        if not self.project_id:
            raise DraftError("project_schema")
        self._run([
            "project", "item-edit", "--id", item_id, "--project-id", self.project_id,
            "--field-id", field_id, "--single-select-option-id", option_id,
        ])

    def edit_iteration(self, item_id: str, field_id: str, iteration_id: str) -> None:
        if not self.project_id:
            raise DraftError("project_schema")
        self._run([
            "project", "item-edit", "--id", item_id, "--project-id", self.project_id,
            "--field-id", field_id, "--iteration-id", iteration_id,
        ])

    def develop(self, repo: str, number: int, name: str) -> str:
        listed = self._run(["issue", "develop", str(number), "--repo", repo, "--list"])
        if name in listed:
            return name
        self._run(["issue", "develop", str(number), "--repo", repo, "--name", name])
        return name


def _json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DraftError("gh_error") from exc


def find_field(fields: list[dict], kind: str) -> dict:
    aliases = FIELD_ALIASES[kind]
    for field in fields:
        name = str(field.get("name") or "").strip().lower()
        if name in aliases:
            return field
    raise DraftError("project_schema", kind)


def match_option(field: dict, wanted: str) -> str:
    options = field.get("options") or []
    wanted_l = wanted.strip().lower()
    for opt in options:
        if str(opt.get("name") or "").strip().lower() == wanted_l:
            oid = opt.get("id")
            if oid:
                return str(oid)
    raise DraftError("pending_meta", field.get("name") or "option")


def current_iteration_id(field: dict, today: date, wanted: str | None) -> str:
    iterations = field.get("iterations") or []
    if wanted:
        w = wanted.strip().lower()
        for it in iterations:
            title = str(it.get("title") or it.get("name") or "").strip().lower()
            if title == w and it.get("id"):
                return str(it["id"])
        raise DraftError("pending_meta", "sprint")
    for it in iterations:
        start = it.get("startDate") or it.get("start_date")
        duration = it.get("duration")
        iid = it.get("id")
        if not start or duration in (None, "") or not iid:
            continue
        try:
            begin = date.fromisoformat(str(start)[:10])
            days = int(duration)
        except (TypeError, ValueError):
            continue
        from datetime import timedelta
        if begin <= today < begin + timedelta(days=days):
            return str(iid)
    raise DraftError("pending_meta", "sprint")
