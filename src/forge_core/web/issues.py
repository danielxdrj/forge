"""Rotas de issues concluídas. Importar: owner + CSRF. Listar relacionadas: editor ou owner."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError
from ..issues.importer import CompletedIssueImporter, IssueImportError
from ..issues.related import TOP_N, find_related
from ..notes.service import NoteRuleError, parse_issue_key


def register_issue_import_routes(
    app: FastAPI,
    importer: CompletedIssueImporter,
    *,
    json_error,
    need_editor_or_owner,
    need_owner,
    audit,
    graph_dir: str | None = None,
):
    def _rule(exc: IssueImportError) -> JSONResponse:
        status = {
            "busy": 409,
            "gh_missing": 503,
            "gh_not_logged": 503,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/completed-issues")
    def api_completed_issues(request: Request, issue: str = "", limit: int = TOP_N):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        if not (issue or "").strip():
            return {"issues": []}
        try:
            key = parse_issue_key(issue)
        except NoteRuleError as exc:
            return json_error(400, exc.code)
        repo_name, _sep, raw_number = key.partition("#")
        try:
            number = int(raw_number)
        except ValueError:
            return json_error(400, "invalid_issue")
        query = _query_for(app.state.repo, repo_name, number, key)
        related = find_related(
            app.state.repo, query, repo_name,
            exclude=(repo_name, number),
            graph_dir=graph_dir,
            limit=limit,
        )
        public = []
        for item in related:
            item.pop("body_excerpt", None)
            public.append(item)
        return {"issues": public}

    @app.post("/api/completed-issues/import")
    def api_import_completed(request: Request):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            result = importer.run(reason="manual", actor=principal.identity_id)
        except IssueImportError as exc:
            audit(principal.identity_id, "issues.import", "repos:*", f"error: {exc.code}")
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        return result


def _query_for(repo, full_repo: str, number: int, key: str) -> str:
    rows = repo.fetch(
        "SELECT title, body FROM completed_issues WHERE lower(repo) = lower(?) AND number = ?",
        (full_repo, number),
    )
    if rows:
        return f"{rows[0][0] or ''} {rows[0][1] or ''}"
    notes = repo.fetch(
        "SELECT title, body FROM investigation_notes WHERE issue_key = ? ORDER BY updated_at DESC, id LIMIT 3",
        (key,),
    )
    bits = [key]
    for title, body in notes:
        bits.append(title or "")
        bits.append((body or "")[:400])
    return " ".join(bits)
