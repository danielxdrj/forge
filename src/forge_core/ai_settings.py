"""Configurações de IA do painel: agenda do radar e motor/modelo por uso.

Ficam em `app_settings` (migração 0022) para o owner mudar pela tela, sem reiniciar.
Usos: `radar` (resumo do radar de prioridades) e `investigation` (investigação).

Motores:
- `cli`: o motor do servidor (FORGE_ENGINE: Claude Code CLI pela assinatura, ou Cursor);
- `api`: API da Anthropic (SDK oficial). Só pode ser escolhido com a chave configurada.

Modelo vazio no `cli` = o padrão da CLI. No `api`, vazio = Claude Opus 5.5.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from .auth.store import AuthStore, Principal
from .draft.anthropic_api import AnthropicApiAdapter, api_key_configured
from .draft.claude_cli import READONLY_DISALLOWED_TOOLS, ClaudeCliAdapter
from .draft.engine import select_engine_adapter
from .errors import AuthorizationError, DraftError, ForgeError
from .storage.sql import SqlRepository

USES = ("radar", "investigation")
ENGINES = ("cli", "api")
MODELS = (
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "hint": "mais capaz; mais caro"},
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "hint": "equilíbrio entre qualidade e custo"},
    {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "hint": "mais barato; bom para resumos curtos"},
)
MODEL_IDS = frozenset(m["id"] for m in MODELS)
_HHMM = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

DEFAULTS = {
    "radar.auto": "false",
    "radar.time": "13:00",
    "radar.engine": "cli",
    "radar.model": "",
    "investigation.engine": "cli",
    "investigation.model": "",
}
# Esforço e teto de saída por uso na API: o resumo do radar é curto e simples.
API_PROFILE = {
    "radar": {"effort": "low", "max_tokens": 2048},
    "investigation": {"effort": "medium", "max_tokens": 16000},
}
CLI_MAX_TURNS = {"radar": 2}


class SettingsError(ForgeError):
    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


class AiSettings:
    def __init__(self, repo: SqlRepository, store: AuthStore | None = None, *, env: Mapping[str, str] | None = None):
        self._repo = repo
        self._store = store
        self._env = env

    # --- leitura ---

    def values(self) -> dict:
        out = dict(DEFAULTS)
        for key, value in self._repo.fetch("SELECT key, value FROM app_settings"):
            if key in out:
                out[key] = value
        return out

    def radar_schedule(self) -> tuple[bool, str]:
        v = self.values()
        time = v["radar.time"] if _HHMM.fullmatch(v["radar.time"] or "") else DEFAULTS["radar.time"]
        return v["radar.auto"] == "true", time

    def api_configured(self) -> bool:
        return api_key_configured(self._env if self._env is not None else os.environ)

    def view(self, principal: Principal) -> dict:
        self._require_reader(principal)
        v = self.values()
        auto, time = self.radar_schedule()
        return {
            "radar": {"auto": auto, "time": time, "engine": v["radar.engine"], "model": v["radar.model"]},
            "investigation": {"engine": v["investigation.engine"], "model": v["investigation.model"]},
            "models": list(MODELS),
            "server_engine": (os.environ.get("FORGE_ENGINE") or "claude").strip().lower() or "claude",
            "api": {"configured": self.api_configured()},
            "can_edit": self._store.has_role(principal.identity_id, "owner") if self._store else False,
        }

    # --- escrita ---

    def update(self, principal: Principal, payload: dict) -> dict:
        if self._store is None:
            raise AuthorizationError("forbidden")
        self._store.require(principal, "owner")
        if not isinstance(payload, dict):
            raise SettingsError("invalid_json")
        changes: dict[str, str] = {}
        radar = payload.get("radar")
        if radar is not None:
            if not isinstance(radar, dict):
                raise SettingsError("invalid_json")
            if "auto" in radar:
                if not isinstance(radar["auto"], bool):
                    raise SettingsError("invalid_auto")
                changes["radar.auto"] = "true" if radar["auto"] else "false"
            if "time" in radar:
                time = str(radar["time"] or "").strip()
                if not _HHMM.fullmatch(time):
                    raise SettingsError("invalid_time")
                changes["radar.time"] = time
            changes.update(self._engine_changes("radar", radar))
        investigation = payload.get("investigation")
        if investigation is not None:
            if not isinstance(investigation, dict):
                raise SettingsError("invalid_json")
            changes.update(self._engine_changes("investigation", investigation))
        if not changes:
            return self.view(principal)
        ts = datetime.now(UTC).isoformat()
        with self._repo.transaction() as tx:
            for key, value in changes.items():
                exists = tx.execute("SELECT 1 FROM app_settings WHERE key = ?", (key,)).fetchone()
                if exists:
                    tx.execute(
                        "UPDATE app_settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = ?",
                        (value, ts, principal.identity_id, key),
                    )
                else:
                    tx.execute(
                        "INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?)",
                        (key, value, ts, principal.identity_id),
                    )
            tx.audit(
                principal.identity_id, "settings.ai_update", "app_settings",
                "ok: " + ", ".join(f"{k}={v or 'padrão'}" for k, v in sorted(changes.items())),
            )
        return self.view(principal)

    def _engine_changes(self, use: str, data: dict) -> dict[str, str]:
        out = {}
        if "engine" in data:
            engine = str(data["engine"] or "").strip()
            if engine not in ENGINES:
                raise SettingsError("invalid_engine")
            if engine == "api" and not self.api_configured():
                raise SettingsError("anthropic_not_configured")
            out[f"{use}.engine"] = engine
        if "model" in data:
            model = str(data["model"] or "").strip()
            if model and model not in MODEL_IDS:
                raise SettingsError("invalid_model")
            out[f"{use}.model"] = model
        return out

    # --- motor ---

    def adapter_for(self, use: str, env: Mapping[str, str] | None = None):
        """Adaptador do motor configurado para o uso. Sempre somente leitura."""
        if use not in USES:
            raise SettingsError("invalid_use")
        env = env if env is not None else (self._env if self._env is not None else os.environ)
        v = self.values()
        engine = v[f"{use}.engine"]
        model = v[f"{use}.model"] or None
        if engine == "api":
            if not api_key_configured(env):
                raise DraftError("anthropic_not_configured")
            profile = API_PROFILE[use]
            return AnthropicApiAdapter(env=env, model=model, effort=profile["effort"], max_tokens=profile["max_tokens"])
        timeout = int(env.get("FORGE_CLAUDE_TIMEOUT", "120") or 120)
        adapter = select_engine_adapter(env, timeout=timeout)
        if isinstance(adapter, ClaudeCliAdapter):
            adapter.permission_mode = "plan"
            adapter.disallowed_tools = READONLY_DISALLOWED_TOOLS
            if model:
                adapter.model = model
            if use in CLI_MAX_TURNS:
                adapter.max_turns = CLI_MAX_TURNS[use]
        return adapter

    def _require_reader(self, principal: Principal) -> None:
        if self._store is None:
            return
        self._store.require_session(principal)
        ident = principal.identity_id
        if self._store.has_role(ident, "editor") or self._store.has_role(ident, "owner"):
            return
        raise AuthorizationError("forbidden")
