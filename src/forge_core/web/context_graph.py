"""GET /api/context-graph: teia combinada. Editor ou owner. Sem corpo de nota."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError
from ..graphs.context import ContextGraph
from ..graphs.indexer import GraphError


def register_context_graph_routes(
    app: FastAPI,
    builder: ContextGraph,
    *,
    json_error,
    need_editor_or_owner,
):
    def _rule(exc: GraphError) -> JSONResponse:
        status = {
            "not_indexed": 404,
            "repo_not_allowed": 400,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/context-graph")
    def api_context_graph(
        request: Request,
        repo: str = "",
        types: str = "",
        q: str = "",
        limit: int = 0,
    ):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return builder.build(repo=repo, types=types, q=q, limit=limit)
        except GraphError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
