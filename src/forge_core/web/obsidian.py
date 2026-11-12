"""Rotas somente leitura do vault Obsidian. Sem envio ao LLM (fase 2)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import AuthorizationError
from ..obsidian.vault import ObsidianVault, VaultRuleError


def register_obsidian_routes(
    app: FastAPI,
    vault: ObsidianVault,
    *,
    json_error,
    need_editor_or_owner,
):
    def _rule(exc: VaultRuleError) -> JSONResponse:
        status = {
            "not_found": 404,
            "vault_disabled": 503,
            "file_too_large": 413,
            "path_forbidden": 403,
        }.get(exc.code, 400)
        return json_error(status, exc.code, hint=exc.hint or None)

    @app.get("/api/vault")
    def api_vault_status(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        return vault.status()

    @app.get("/api/vault/notes")
    def api_vault_list(request: Request):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        status = vault.status()
        if not status["enabled"]:
            return status
        try:
            return vault.list_notes()
        except VaultRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")

    @app.get("/api/vault/notes/{note_path:path}")
    def api_vault_read(request: Request, note_path: str):
        principal = need_editor_or_owner(request)
        if isinstance(principal, JSONResponse):
            return principal
        try:
            return vault.read_note(note_path)
        except VaultRuleError as exc:
            return _rule(exc)
        except AuthorizationError:
            return json_error(403, "forbidden")
