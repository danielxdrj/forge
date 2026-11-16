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
IMPORT_MAX_OUTPUT = 512 * 1024
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

DONE_ITEMS_QUERY = """
query($id: ID!, $first: Int!, $after: String) {
  node(id: $id) {
    ... on ProjectV2 {
      items(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                field { ... on ProjectV2IterationField { name } }
              }
            }
          }
          content {
            ... on Issue {
              number
              title
              url
              closedAt
              repository { nameWithOwner }
              labels(first: 20) { nodes { name } }
            }
          }
        }
      }
    }
  }
}
"""

ISSUE_IMPORT_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      number
      title
      body
      url
      closedAt
      state
      labels(first: 20) { nodes { name } }
      closedByPullRequestsReferences(first: 10) {
        nodes { number url title }
      }
    }
  }
}
"""

DELETE_ISSUE_MUTATION = """
mutation($id: ID!) {
  deleteIssue(input: {issueId: $id}) {
    clientMutationId
  }
}
"""
_DELETE_FORBIDDEN_MARKERS = (
    "not accessible", "resource not accessible", "must have admin",
    "must be an administrator", "403", "forbidden", "insufficient",
)

DEFAULT_HEAD_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      name
      target { oid }
    }
  }
}
"""
_SHA = re.compile(r"^[a-fA-F0-9]{7,64}$")

DONE_STATUS_ALIASES = frozenset({
    "done", "concluido", "concluído", "pronto", "finished", "complete", "completed",
})
STATUS_FIELD_ALIASES = frozenset({"status", "estado", "situacao", "situação"})


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

    def _run(
        self, args: list[str], *, cwd: str | None = None, timeout: int | None = None,
        max_output: int | None = None, classify: Callable[[str], str | None] | None = None,
    ) -> str:
        argv = [self.bin, *args]
        self.calls.append(argv)
        run = self._runner or subprocess.run
        try:
            proc = run(
                argv, cwd=cwd, env=self._env_os(), capture_output=True, check=False,
                shell=False, timeout=timeout or self.timeout,
            )
        except FileNotFoundError as exc:
            raise DraftError("gh_missing") from exc
        except subprocess.TimeoutExpired as exc:
            raise DraftError("timeout") from exc
        raw = proc.stdout or b""
        if len(raw) > (max_output or MAX_OUTPUT):
            raise DraftError("output_too_large")
        text = raw.decode("utf-8", "replace")
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").lower()
            if classify is not None:
                code = classify(err)
                if code:
                    raise DraftError(code)
            if "project" in err and ("scope" in err or "403" in err or "resource not accessible" in err):
                raise DraftError("project_scope", "gh auth refresh -s project")
            if "release not found" in err or "no releases found" in err:
                raise DraftError("no_release")
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

    def clone_repo_at(self, repo: str, dest: str, tag: str) -> None:
        """Clona uma tag de release ou a branch padrão (`git clone --branch REF`). Sem token no env."""
        tag = (tag or "").strip()
        if not tag or tag.startswith("-") or ".." in tag or "\x00" in tag:
            raise DraftError("gh_error")
        self._run(
            ["repo", "clone", repo, dest, "--", "--branch", tag, "--depth", "1", "--single-branch"],
            timeout=180,
        )

    def latest_release_tag(self, repo: str) -> str:
        try:
            text = self._run(["release", "view", "--repo", repo, "--json", "tagName,targetCommitish"])
        except DraftError:
            raise
        data = _json(text)
        if not isinstance(data, dict):
            raise DraftError("no_release")
        tag = str(data.get("tagName") or "").strip()
        if not tag:
            raise DraftError("no_release")
        return tag

    def default_branch_head(self, repo: str) -> tuple[str, str]:
        """Branch padrão e SHA do HEAD. Somente leitura (GraphQL). Sem token no env."""
        owner, _, name = (repo or "").partition("/")
        if not owner or not name or "/" in name:
            raise DraftError("gh_error")
        text = self._run([
            "api", "graphql",
            "-F", f"owner={owner}",
            "-F", f"name={name}",
            "-f", f"query={DEFAULT_HEAD_QUERY}",
        ])
        payload = _json(text)
        ref = (((payload.get("data") or {}).get("repository") or {}).get("defaultBranchRef") or {})
        if not isinstance(ref, dict):
            raise DraftError("gh_error")
        branch = str(ref.get("name") or "").strip()
        target = ref.get("target") if isinstance(ref.get("target"), dict) else {}
        sha = str(target.get("oid") or "").strip()
        if not branch or branch.startswith("-") or ".." in branch or "\x00" in branch:
            raise DraftError("gh_error")
        if not _SHA.fullmatch(sha):
            raise DraftError("gh_error")
        return branch, sha

    def list_issues(self, repo: str, limit: int = 50) -> list[IssueRef]:
        cap = max(1, min(int(limit), 100))
        text = self._run([
            "issue", "list", "--repo", repo, "--limit", str(cap),
            "--state", "all", "--json", "number,title,url,state",
        ])
        data = _json(text)
        if not isinstance(data, list):
            raise DraftError("gh_error")
        out: list[IssueRef] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                out.append(IssueRef(
                    int(item["number"]), str(item.get("url") or ""),
                    item.get("title"), item.get("state"),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

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

    def list_closed_issues(self, repo: str, limit: int = 50) -> list[dict]:
        """Lista issues fechadas. Somente leitura; sem corpo."""
        cap = max(1, min(int(limit), 100))
        text = self._run([
            "issue", "list", "--repo", repo, "--limit", str(cap),
            "--state", "closed", "--json", "number,title,url,closedAt,labels,state",
        ])
        data = _json(text)
        if not isinstance(data, list):
            raise DraftError("gh_error")
        out: list[dict] = []
        for item in data:
            parsed = _issue_list_item(item, repo)
            if parsed is not None:
                out.append(parsed)
        return out

    def list_done_project_issues(self, allowed_repos: set[str], limit: int = 100) -> list[dict]:
        """Issues na coluna Done do board IT Backlog. Somente leitura. Pagina até `limit`."""
        cap = max(1, min(int(limit), 200))
        try:
            self.preflight()
        except DraftError as exc:
            if exc.code in {"project_scope", "project_schema"}:
                return []
            raise
        if not self.project_id:
            return []
        allowed = {name.lower() for name in allowed_repos}
        out: list[dict] = []
        after = None
        page = 50
        while len(out) < cap:
            args = [
                "api", "graphql",
                "-F", f"id={self.project_id}",
                "-F", f"first={page}",
            ]
            if after:
                args.extend(["-F", f"after={after}"])
            args.extend(["-f", f"query={DONE_ITEMS_QUERY}"])
            text = self._run(args, max_output=IMPORT_MAX_OUTPUT)
            payload = _json(text)
            items = (((payload.get("data") or {}).get("node") or {}).get("items") or {})
            nodes = items.get("nodes")
            if not isinstance(nodes, list):
                break
            for node in nodes:
                parsed = _done_item(node, allowed)
                if parsed is not None:
                    out.append(parsed)
                    if len(out) >= cap:
                        break
            info = items.get("pageInfo") or {}
            if not info.get("hasNextPage") or not info.get("endCursor"):
                break
            after = str(info["endCursor"])
        return out[:cap]

    def view_completed_issue(self, repo: str, number: int) -> dict:
        """Detalhe de issue fechada + PRs ligados. Somente leitura. Sem mutação."""
        owner, _, name = repo.partition("/")
        if not owner or not name:
            raise DraftError("gh_error")
        try:
            text = self._run([
                "api", "graphql",
                "-F", f"owner={owner}",
                "-F", f"name={name}",
                "-F", f"number={int(number)}",
                "-f", f"query={ISSUE_IMPORT_QUERY}",
            ], max_output=IMPORT_MAX_OUTPUT)
            payload = _json(text)
            issue = (((payload.get("data") or {}).get("repository") or {}).get("issue"))
            if not isinstance(issue, dict):
                raise DraftError("gh_error")
            return self._hydrate_issue(repo, issue)
        except DraftError:
            text = self._run([
                "issue", "view", str(number), "--repo", repo,
                "--json", "number,title,body,url,closedAt,labels,state",
            ], max_output=IMPORT_MAX_OUTPUT)
            data = _json(text)
            if not isinstance(data, dict) or "number" not in data:
                raise DraftError("gh_error")
            return self._hydrate_issue(repo, data)

    def pr_changed_files(self, repo: str, number: int) -> list[str]:
        """Arquivos de um PR. Somente leitura."""
        text = self._run([
            "pr", "view", str(number), "--repo", repo, "--json", "files,number,url",
        ])
        data = _json(text)
        if not isinstance(data, dict):
            return []
        return _file_paths(data.get("files"))

    def _hydrate_issue(self, repo: str, raw: dict) -> dict:
        number = int(raw.get("number") or 0)
        labels = _label_names(raw.get("labels"))
        prs = []
        refs = raw.get("closedByPullRequestsReferences") or {}
        nodes = refs.get("nodes") if isinstance(refs, dict) else refs
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict) or not node.get("number"):
                    continue
                pr_number = int(node["number"])
                pr_url = str(node.get("url") or "")
                pr_repo = _repo_from_pr_url(pr_url) or repo
                try:
                    files = self.pr_changed_files(pr_repo, pr_number)
                except DraftError:
                    files = []
                prs.append({
                    "number": pr_number,
                    "url": pr_url,
                    "title": str(node.get("title") or ""),
                    "files": files,
                })
        tipo, prioridade, sprint = _labels_to_fields(labels)
        return {
            "repo": repo,
            "number": number,
            "title": str(raw.get("title") or ""),
            "body": str(raw.get("body") or ""),
            "url": str(raw.get("url") or ""),
            "closed_at": str(raw.get("closedAt") or raw.get("closed_at") or "") or None,
            "state": str(raw.get("state") or ""),
            "labels": labels,
            "tipo": tipo,
            "prioridade": prioridade,
            "sprint": sprint,
            "prs": prs,
        }

    def node_id_of_issue(self, repo: str, number: int) -> str:
        owner, _, name = (repo or "").partition("/")
        if not owner or not name:
            raise DraftError("gh_error")
        text = self._run(["api", f"repos/{owner}/{name}/issues/{int(number)}", "--jq", ".node_id"])
        node_id = text.strip()
        if not node_id:
            raise DraftError("gh_error")
        return node_id

    def delete_issue(self, repo: str, number: int) -> None:
        """Apaga a issue (mutation GraphQL `deleteIssue`). Exige permissão de admin no repositório."""
        node_id = self.node_id_of_issue(repo, number)

        def classify(err: str) -> str | None:
            if any(marker in err for marker in _DELETE_FORBIDDEN_MARKERS):
                return "issue_delete_forbidden"
            return None

        self._run(
            ["api", "graphql", "-f", f"query={DELETE_ISSUE_MUTATION}", "-F", f"id={node_id}"],
            classify=classify,
        )

    def close_issue_not_planned(self, repo: str, number: int) -> None:
        """Fallback quando apagar é recusado por falta de permissão: fecha como `not planned`."""
        self._run(["issue", "close", str(number), "--repo", repo, "--reason", "not planned"])

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


def _label_names(raw) -> list[str]:
    names: list[str] = []
    nodes = raw
    if isinstance(raw, dict):
        nodes = raw.get("nodes") or raw.get("edges") or []
    if not isinstance(nodes, list):
        return names
    for item in nodes:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _file_paths(raw) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("filename") or "").strip()
        if path:
            out.append(path)
    return out


def _labels_to_fields(labels: list[str]) -> tuple[str, str, str]:
    tipo = prioridade = sprint = ""
    for name in labels:
        low = name.strip()
        folded = fold_option_name(low)
        for prefix, target in (
            ("tipo:", "tipo"), ("type:", "tipo"),
            ("prioridade:", "prioridade"), ("priority:", "prioridade"),
            ("sprint:", "sprint"),
        ):
            if folded.startswith(prefix):
                value = name.split(":", 1)[1].strip()
                if target == "tipo" and not tipo:
                    tipo = value
                elif target == "prioridade" and not prioridade:
                    prioridade = value
                elif target == "sprint" and not sprint:
                    sprint = value
    return tipo, prioridade, sprint


def _repo_from_pr_url(url: str) -> str | None:
    text = (url or "").strip()
    marker = "github.com/"
    if marker not in text or "/pull/" not in text:
        return None
    rest = text.split(marker, 1)[1]
    parts = rest.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def _issue_list_item(item, default_repo: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    try:
        number = int(item["number"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "repo": default_repo,
        "number": number,
        "title": str(item.get("title") or ""),
        "url": str(item.get("url") or ""),
        "closed_at": str(item.get("closedAt") or "") or None,
        "labels": _label_names(item.get("labels")),
        "tipo": "",
        "prioridade": "",
        "sprint": "",
    }


def _done_item(node, allowed: set[str]) -> dict | None:
    if not isinstance(node, dict):
        return None
    content = node.get("content")
    if not isinstance(content, dict) or not content.get("number"):
        return None
    repo = str((content.get("repository") or {}).get("nameWithOwner") or "").strip()
    if repo.lower() not in allowed:
        return None
    fields = _project_field_map(node.get("fieldValues"))
    status = fold_option_name(fields.get("status") or "")
    if status and status not in DONE_STATUS_ALIASES:
        return None
    if not status:
        return None
    try:
        number = int(content["number"])
    except (TypeError, ValueError):
        return None
    labels = _label_names(content.get("labels"))
    tipo = fields.get("tipo") or ""
    prioridade = fields.get("prioridade") or ""
    sprint = fields.get("sprint") or ""
    if not tipo or not prioridade or not sprint:
        lt, lp, ls = _labels_to_fields(labels)
        tipo = tipo or lt
        prioridade = prioridade or lp
        sprint = sprint or ls
    return {
        "repo": repo,
        "number": number,
        "title": str(content.get("title") or ""),
        "url": str(content.get("url") or ""),
        "closed_at": str(content.get("closedAt") or "") or None,
        "labels": labels,
        "tipo": tipo,
        "prioridade": prioridade,
        "sprint": sprint,
    }


def _project_field_map(raw) -> dict[str, str]:
    nodes = raw
    if isinstance(raw, dict):
        nodes = raw.get("nodes") or []
    if not isinstance(nodes, list):
        return {}
    out: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        field = node.get("field") or {}
        fname = fold_option_name(str(field.get("name") or ""))
        value = str(node.get("name") or node.get("title") or "").strip()
        if not fname or not value:
            continue
        if fname in STATUS_FIELD_ALIASES:
            out["status"] = value
        elif fname in FIELD_ALIASES["tipo"]:
            out["tipo"] = value
        elif fname in FIELD_ALIASES["prioridade"]:
            out["prioridade"] = value
        elif fname in FIELD_ALIASES["sprint"]:
            out["sprint"] = value
    return out


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
