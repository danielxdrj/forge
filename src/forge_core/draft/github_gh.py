"""Porta do GitHub CLI local. Sessão nativa do gh (keyring). Sem GH_TOKEN no env.

`gh issue create` imprime a URL (não tem --json). Número: parse da URL e
`gh issue view URL --json number,url`. Iterações: GraphQL documentado
(https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects),
porque `gh project field-list` não devolve configuration.iterations.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from ..errors import DraftError
from .envfilter import GH_ENV_ALLOW, filter_env
from .template import PROJECT_NUMBER, PROJECT_OWNER

Runner = Callable[..., subprocess.CompletedProcess]
MAX_OUTPUT = 256 * 1024
DEFAULT_TIMEOUT = 60
ISSUE_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/issues/(\d+)")

FIELD_ALIASES = {
    "sprint": ("sprint", "sprint semana", "iteration", "iteração"),
    "tipo": ("tipo", "type"),
    "prioridade": ("prioridade", "priority"),
    "size": ("size", "tamanho"),
    "escopo": ("escopo", "scope"),
}

# Query oficial (campos extra title/duration existem no tipo GraphQL ProjectV2IterationFieldIteration).
FIELDS_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on ProjectV2 {
      fields(first: 100) {
        nodes {
          ... on ProjectV2Field { id name }
          ... on ProjectV2IterationField {
            id name
            configuration {
              iterations { id startDate duration title }
              completedIterations { id startDate duration title }
            }
          }
          ... on ProjectV2SingleSelectField {
            id name
            options { id name }
          }
        }
      }
    }
  }
}
"""

ITEM_VALUES_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on ProjectV2Item {
      fieldValues(first: 50) {
        nodes {
          ... on ProjectV2ItemFieldSingleSelectValue {
            name
            field { ... on ProjectV2SingleSelectField { id name } }
          }
          ... on ProjectV2ItemFieldIterationValue {
            title
            field { ... on ProjectV2IterationField { id name } }
          }
        }
      }
    }
  }
}
"""


@dataclass
class IssueRef:
    number: int
    url: str
    title: str | None = None
    state: str | None = None


@dataclass
class RemoteState:
    issue: int | None = None
    url: str | None = None
    branch: str | None = None
    item_id: str | None = None
    phase: str = "none"
    repo: str | None = None


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
            "--assignee", assignee,
        ])
        if "--json" in text:
            raise DraftError("gh_error")
        match = ISSUE_URL.search(text)
        if not match:
            raise DraftError("gh_error")
        url = match.group(0)
        number = int(match.group(1))
        viewed = self.view_issue(url, repo)
        if viewed.number != number or viewed.url.rstrip("/") != url.rstrip("/"):
            raise DraftError("remote_mismatch")
        return viewed

    def view_issue(self, url_or_number: str, repo: str) -> IssueRef:
        text = self._run([
            "issue", "view", str(url_or_number), "--repo", repo, "--json", "number,url,title,state",
        ])
        data = _json(text)
        try:
            return IssueRef(int(data["number"]), str(data["url"]), data.get("title"), data.get("state"))
        except (KeyError, TypeError, ValueError) as exc:
            raise DraftError("gh_error") from exc

    def view_issue_detail(self, number: int, repo: str) -> dict:
        text = self._run([
            "issue", "view", str(number), "--repo", repo,
            "--json", "number,url,title,body,comments,state",
        ])
        data = _json(text)
        if not isinstance(data, dict) or "number" not in data:
            raise DraftError("gh_error")
        return data

    def clone_repo(self, repo: str, dest: str) -> None:
        self._run(["repo", "clone", repo, dest])

    def list_issue_branches(self, repo: str, number: int) -> list[str]:
        text = self._run(["issue", "develop", str(number), "--repo", repo, "--list"])
        names = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("showing"):
                continue
            token = line.split()[0].strip()
            if token.startswith("http") or "#" in token:
                continue
            if token and token not in names:
                names.append(token)
        return names

    def create_draft_pr(self, repo: str, title: str, body: str, head: str) -> str:
        args = [
            "pr", "create", "--repo", repo, "--title", title, "--body", body,
            "--head", head, "--draft",
        ]
        if any(f in args for f in ("merge", "--merge", "--squash", "--rebase")):
            raise DraftError("unsafe_flags")
        text = self._run(args)
        url = ""
        for token in text.split():
            if "github.com" in token and "/pull/" in token:
                url = token.strip()
                break
        if not url:
            raise DraftError("gh_error")
        return url

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
        """Schema real via GraphQL (iterações e opções). Não usa field-list para Sprint."""
        if not self.project_id:
            raise DraftError("project_schema")
        text = self._run([
            "api", "graphql", "-F", f"id={self.project_id}", "-f", f"query={FIELDS_QUERY}",
        ])
        payload = _json(text)
        nodes = (((payload.get("data") or {}).get("node") or {}).get("fields") or {}).get("nodes")
        if not isinstance(nodes, list):
            raise DraftError("project_schema")
        return [_normalize_field(n) for n in nodes if isinstance(n, dict) and n.get("id")]

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

    def read_item_values(self, item_id: str) -> list[dict]:
        """Relê o item do ProjectV2 (somente leitura). Sem mutação."""
        text = self._run([
            "api", "graphql", "-F", f"id={item_id}", "-f", f"query={ITEM_VALUES_QUERY}",
        ])
        payload = _json(text)
        nodes = (((payload.get("data") or {}).get("node") or {}).get("fieldValues") or {}).get("nodes")
        if not isinstance(nodes, list):
            raise DraftError("board_mismatch", "item")
        out = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            field = node.get("field") or {}
            fid = field.get("id")
            if not fid:
                continue
            out.append({
                "field_id": str(fid),
                "field_name": str(field.get("name") or ""),
                "name": str(node.get("name") or node.get("title") or ""),
            })
        return out

    def develop(self, repo: str, number: int, name: str) -> str:
        listed = self._run(["issue", "develop", str(number), "--repo", repo, "--list"])
        if name in listed:
            return name
        self._run(["issue", "develop", str(number), "--repo", repo, "--name", name])
        return name

    def find_pr(self, repo: str, head: str) -> str | None:
        """Procura PR existente pela branch. Somente leitura; não cria PR."""
        if not (repo or "").strip() or not (head or "").strip():
            return None
        try:
            text = self._run([
                "pr", "list", "--repo", repo, "--head", head, "--state", "all",
                "--json", "url,number", "--limit", "1",
            ])
            data = _json(text)
        except DraftError:
            return None
        if not isinstance(data, list) or not data:
            return None
        url = str((data[0] or {}).get("url") or "").strip()
        return url or None


def _json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DraftError("gh_error") from exc


def _normalize_field(node: dict) -> dict:
    cfg = node.get("configuration") or {}
    iterations = list(cfg.get("iterations") or []) + list(cfg.get("completedIterations") or [])
    return {
        "id": node["id"],
        "name": node.get("name") or "",
        "options": node.get("options") or [],
        "iterations": iterations,
    }


def find_field(fields: list[dict], kind: str) -> dict:
    aliases = FIELD_ALIASES[kind]
    for field in fields:
        name = str(field.get("name") or "").strip().lower()
        if name in aliases:
            return field
    raise DraftError("project_schema", kind)


def fold_option_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().strip()
    text = re.sub(r"^[^\w]+", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def names_match(actual: str, wanted: str) -> bool:
    a, w = fold_option_name(actual), fold_option_name(wanted)
    if not a or not w:
        return False
    return a == w or a.endswith(w) or w.endswith(a)


def canonical_board_value(names: list[str], wanted: str) -> str | None:
    """Devolve o nome canônico da opção do board, ou None se não houver correspondência única."""
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    exact = [n for n in names if fold_option_name(n) == fold_option_name(wanted)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    loose = [n for n in names if names_match(n, wanted)]
    if len(loose) == 1:
        return loose[0]
    return None


def match_option(field: dict, wanted: str) -> str:
    options = field.get("options") or []
    exact, loose = [], []
    for opt in options:
        name = str(opt.get("name") or "")
        folded = fold_option_name(name)
        want = fold_option_name(wanted)
        if folded == want:
            exact.append(opt)
        elif names_match(name, wanted):
            loose.append(opt)
    chosen = exact or loose
    if len(chosen) != 1 or not chosen[0].get("id"):
        raise DraftError("pending_meta", field.get("name") or "option")
    return str(chosen[0]["id"])


def current_iteration_id(field: dict, today: date, wanted: str | None) -> str:
    iterations = field.get("iterations") or []
    if wanted and wanted.strip():
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
        if begin <= today < begin + timedelta(days=days):
            return str(iid)
    raise DraftError("pending_meta", "sprint")
