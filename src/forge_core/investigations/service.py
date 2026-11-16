"""Investigação livre (sem issue obrigatória): roda o motor configurado em modo
somente leitura sobre a descrição da pessoa, a seção do grafo e (se houver)
metadados não-secretos das conexões selecionadas.

Persistido em `investigation_notes` (migração 0018; `kind='investigation'`, reaproveita
a mesma tabela das notas manuais). Nunca inclui segredo de conexão nem conteúdo do vault
Obsidian: o prompt é composto só de descrição, grafo de código e metadados de conexão
(nome/tipo/usuário/porta, nunca o segredo cifrado).
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from ..auth.store import AuthStore, Principal
from ..draft.claude_cli import READONLY_DISALLOWED_TOOLS, ClaudeCliAdapter
from ..draft.engine import select_engine_adapter
from ..errors import AuthorizationError, DraftError, ForgeError
from ..graphs.prompt_context import graph_prompt_section
from ..notes.service import NoteRuleError, parse_issue_key
from ..redaction import redact_secrets
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository

MAX_DESCRIPTION_BYTES = 8 * 1024
MAX_TITLE = 200
MAX_REPOS = 10
MAX_CONNECTIONS = 10
MAX_RESULT_BYTES = 96 * 1024

INSTRUCTION = """Você é o agente de investigação do Forge, em modo SOMENTE LEITURA.
NÃO altere nenhum arquivo, banco de dados, FTP ou Portainer conectado.
NÃO execute git push, gh, nem qualquer comando de rede ou de escrita.
Use só o contexto fornecido abaixo (descrição, grafo de código e metadados de conexão).
Responda em texto: o que foi encontrado, hipóteses e próximos passos sugeridos.
"""


class InvestigationRuleError(ForgeError):
    """Validação ou estado da investigação. Código fixo; nunca inclui segredo."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class InvestigationView:
    id: str
    issue_key: str | None
    title: str
    description: str
    repos: tuple[str, ...]
    connection_ids: tuple[str, ...]
    engine: str
    result: str
    created_by: str
    created_at: str
    updated_at: str

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "issue_key": self.issue_key,
            "title": self.title,
            "description": self.description,
            "repos": list(self.repos),
            "connection_ids": list(self.connection_ids),
            "engine": self.engine,
            "result": self.result,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_editor_or_owner(store: AuthStore, principal: Principal) -> Principal:
    store.require_session(principal)
    ident = principal.identity_id
    if store.has_role(ident, "editor") or store.has_role(ident, "owner"):
        return principal
    store._repo.record_audit(ident, "auth.denied", "role:investigation", "error: forbidden")
    raise AuthorizationError("forbidden")


def _description(raw) -> str:
    if not isinstance(raw, str):
        raise InvestigationRuleError("invalid_description")
    text = raw.strip()
    if not text or len(text.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise InvestigationRuleError("invalid_description")
    return text


def _title_from(description: str) -> str:
    first_line = description.strip().splitlines()[0] if description.strip() else ""
    title = first_line.strip() or "Investigação"
    return title[:MAX_TITLE]


def _capped(text: str, max_bytes: int) -> str:
    encoded = (text or "").encode("utf-8")
    if len(encoded) <= max_bytes:
        return text or ""
    return encoded[:max_bytes].decode("utf-8", "ignore") + "\n[truncado]\n"


class InvestigationService:
    def __init__(
        self,
        repo: SqlRepository,
        store: AuthStore,
        *,
        provider=None,
        graph_dir=None,
        graph_prompt_max_nodes: int | None = None,
        graph_prompt_max_chars: int | None = None,
        claude_max_turns: int | None = None,
        env=None,
    ):
        self._repo = repo
        self._store = store
        self._provider = provider
        self._graph_dir = graph_dir
        self._graph_prompt_max_nodes = graph_prompt_max_nodes
        self._graph_prompt_max_chars = graph_prompt_max_chars
        self._claude_max_turns = claude_max_turns
        self._env = env

    def run(self, principal: Principal, payload: dict) -> InvestigationView:
        _require_editor_or_owner(self._store, principal)
        if not isinstance(payload, dict):
            raise InvestigationRuleError("invalid_json")
        description = _description(payload.get("description"))
        repos = self._validated_repos(payload.get("repos"))
        issue_key = self._optional_issue_key(payload.get("issue_key"))
        connection_ids = self._validated_connection_ids(payload.get("connection_ids"))
        connection_meta = self._connection_metadata(connection_ids)
        prompt = self._build_prompt(description, repos, connection_meta)
        adapter = self._adapter()
        try:
            response = adapter.complete(prompt)
        except DraftError:
            raise
        except Exception as exc:
            raise InvestigationRuleError("provider_error") from exc
        result = _capped(redact_secrets(response.text), MAX_RESULT_BYTES)
        title = _title_from(description)
        inv_id = str(uuid.uuid4())
        ts = _now()
        engine_name = getattr(adapter, "name", "") or ""
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO investigation_notes "
                "(id, issue_key, title, body, created_by, created_at, updated_at, "
                "kind, repos_json, connection_ids_json, engine, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'investigation', ?, ?, ?, ?)",
                (
                    inv_id, issue_key, title, result, principal.identity_id, ts, ts,
                    json.dumps(list(repos), ensure_ascii=False),
                    json.dumps(list(connection_ids), ensure_ascii=False),
                    engine_name, description,
                ),
            )
            tx.audit(
                principal.identity_id, "investigation.run", f"investigation:{inv_id}",
                f"ok: repos={len(repos)} connections={len(connection_ids)} bytes={len(result.encode('utf-8'))}",
            )
        return self._load(inv_id)

    def list_investigations(self, principal: Principal) -> list[InvestigationView]:
        _require_editor_or_owner(self._store, principal)
        rows = self._repo.fetch(
            "SELECT id, issue_key, title, body, created_by, created_at, updated_at, "
            "repos_json, connection_ids_json, engine, description "
            "FROM investigation_notes WHERE kind = 'investigation' ORDER BY updated_at DESC, id",
        )
        return [_view_from_row(row) for row in rows]

    def get_investigation(self, principal: Principal, investigation_id: str) -> InvestigationView:
        _require_editor_or_owner(self._store, principal)
        view = self._load(investigation_id)
        if view is None:
            raise InvestigationRuleError("not_found")
        return view

    def _load(self, investigation_id: str) -> InvestigationView | None:
        rows = self._repo.fetch(
            "SELECT id, issue_key, title, body, created_by, created_at, updated_at, "
            "repos_json, connection_ids_json, engine, description "
            "FROM investigation_notes WHERE kind = 'investigation' AND id = ?",
            (investigation_id,),
        )
        if not rows:
            return None
        return _view_from_row(rows[0])

    def _validated_repos(self, raw) -> tuple[str, ...]:
        if raw is None:
            items: list = []
        elif isinstance(raw, list):
            items = raw
        else:
            raise InvestigationRuleError("invalid_repos")
        if len(items) > MAX_REPOS:
            raise InvestigationRuleError("invalid_repos")
        allowed = {f"{r.owner}/{r.repo_name}".lower(): f"{r.owner}/{r.repo_name}"
                   for r in list_active_allowed_repos(self._repo)}
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            canonical = allowed.get(text.lower())
            if canonical is None:
                raise InvestigationRuleError("repo_not_allowed", text)
            if canonical.lower() not in seen:
                seen.add(canonical.lower())
                out.append(canonical)
        return tuple(out)

    def _optional_issue_key(self, raw) -> str | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            return parse_issue_key(text)
        except NoteRuleError as exc:
            raise InvestigationRuleError(exc.code) from exc

    def _validated_connection_ids(self, raw) -> tuple[str, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, list) or len(raw) > MAX_CONNECTIONS:
            raise InvestigationRuleError("invalid_connection_ids")
        out: list[str] = []
        for item in raw:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
        return tuple(out)

    def _connection_metadata(self, connection_ids: tuple[str, ...]) -> list[dict]:
        """Só metadados não-secretos (nunca `secret_ciphertext`)."""
        out: list[dict] = []
        for cid in connection_ids:
            rows = self._repo.fetch(
                "SELECT id, name, type, username, port, database_name, remote_path "
                "FROM connections WHERE id = ?",
                (cid,),
            )
            if not rows:
                continue
            r = rows[0]
            out.append({
                "id": r[0], "name": r[1], "type": r[2], "user": r[3],
                "port": int(r[4]), "database": r[5], "path": r[6],
            })
        return out

    def _build_prompt(self, description: str, repos: tuple[str, ...], connection_meta: list[dict]) -> str:
        parts = [INSTRUCTION]
        if connection_meta:
            lines = ["## Conexões selecionadas (metadados; sem segredo)"]
            for c in connection_meta:
                extra = f" banco={c['database']}" if c.get("database") else ""
                extra += f" caminho={c['path']}" if c.get("path") else ""
                lines.append(f"- {c['name']} (tipo={c['type']}, usuário={c['user']}, porta={c['port']}){extra}")
            parts.append("\n".join(lines))
        graph_section = ""
        if self._graph_dir and repos:
            try:
                graph_section = graph_prompt_section(
                    self._graph_dir, description, list(repos),
                    max_nodes=self._graph_prompt_max_nodes, max_chars=self._graph_prompt_max_chars,
                )
            except Exception:
                graph_section = ""
        if graph_section:
            parts.append(graph_section)
        parts.append("## Pergunta da pessoa\n" + description)
        prompt = "\n\n".join(parts)
        if "FORGE_" in prompt or "GH_TOKEN" in prompt or "GITHUB_TOKEN" in prompt:
            raise InvestigationRuleError("secret_in_prompt")
        return prompt

    def _adapter(self):
        if self._provider is not None:
            return self._provider
        env = self._env or os.environ
        timeout = int(env.get("FORGE_CLAUDE_TIMEOUT", "120") or 120)
        adapter = select_engine_adapter(env, timeout=timeout)
        if isinstance(adapter, ClaudeCliAdapter):
            adapter.permission_mode = "plan"
            adapter.disallowed_tools = READONLY_DISALLOWED_TOOLS
            if self._claude_max_turns is not None:
                adapter.max_turns = self._claude_max_turns
        return adapter


def _view_from_row(row) -> InvestigationView:
    (ident, issue_key, title, body, created_by, created_at, updated_at,
     repos_json, connection_ids_json, engine, description) = row
    repos = tuple(_loads_list(repos_json))
    connection_ids = tuple(_loads_list(connection_ids_json))
    return InvestigationView(
        id=ident, issue_key=issue_key, title=title, description=description or "",
        repos=repos, connection_ids=connection_ids, engine=engine or "", result=body,
        created_by=created_by, created_at=created_at, updated_at=updated_at,
    )


def _loads_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []
