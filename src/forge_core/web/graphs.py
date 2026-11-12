"""Rotas do índice Graphify. Leitura: editor ou owner. Atualizar: só owner.

O segundo refresh enquanto indexa devolve o progresso (200), sem HTTP 409.
"""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError
from ..graphs.indexer import GraphError, GraphIndexer


def register_graph_routes(
    app: FastAPI,
    indexer: GraphIndexer,
    *,
    json_error,
    need_editor_or_owner,
    need_owner,
    audit,
):
    def _rule(exc: GraphError) -> JSONResponse:
        status = {
            "not_indexed": 404,
            "repo_not_allowed": 400,
            "gh_missing": 503,
            "gh_not_logged": 503,
            "graphify_missing": 503,
            "timeout": 504,
            "too_large": 413,
            "missing_output": 502,
            "invalid_json": 502,
            "schema": 502,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/graphs")
    def api_graphs(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        progress = indexer.progress()
        return {"graphs": indexer.status(), **progress}

    @app.get("/api/graphs/status")
    def api_graph_status(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        return indexer.progress()

    @app.get("/api/graphs/nodes")
    def api_graph_nodes(request: Request, repo: str = "", q: str = ""):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return indexer.query(repo, q)
        except GraphError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.post("/api/graphs/refresh")
    async def api_graph_refresh(request: Request):
        principal = need_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        repo = None
        try:
            raw = await request.body()
            if raw:
                body = json.loads(raw.decode("utf-8"))
                if isinstance(body, dict) and body.get("repo"):
                    repo = str(body["repo"])
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return json_error(400, "invalid_json")
        try:
            result = indexer.request_refresh(repo, reason="manual")
        except GraphError as exc:
            audit(principal.identity_id, "graph.refresh", f"repo:{repo or '*'}", f"error: {exc.code}")
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
        target = f"repo:{repo}" if repo else "repo:*"
        if result.get("accepted"):
            audit(principal.identity_id, "graph.refresh", target, "ok: started")
        else:
            audit(principal.identity_id, "graph.refresh", target, "ok: running")
        return result
