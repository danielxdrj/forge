"""Configurações de IA (agenda do radar, motor e modelo por uso) e adaptador da API da Anthropic."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from auth_helpers import actor

from forge_core.ai_settings import AiSettings, SettingsError
from forge_core.auth.store import AuthStore
from forge_core.draft.anthropic_api import (
    AnthropicApiAdapter,
    api_key_configured,
    estimate_cost,
    read_api_key,
)
from forge_core.draft.claude_cli import ClaudeCliAdapter
from forge_core.errors import AuthorizationError, DraftError
from forge_core.storage.migrate import pending_migrations

KEY_PLACEHOLDER = "sk-ant-teste-<SEGREDO>"


def _ai(repo, env=None):
    return AiSettings(repo, AuthStore(repo), env=env if env is not None else {})


def test_0022_listed_and_table_exists(make_repo):
    assert any(p.stem.startswith("0022_app_settings") for p in pending_migrations("sqlite"))
    assert any(p.stem.startswith("0022_app_settings") for p in pending_migrations("postgres"))
    make_repo().fetch("SELECT key, value, updated_at, updated_by FROM app_settings LIMIT 0")


def test_defaults_and_view(make_repo):
    repo = make_repo()
    ai = _ai(repo)
    ana = actor(repo, "ana")
    view = ai.view(ana)
    assert view["radar"] == {"auto": True, "time": "11:00", "engine": "cli", "model": ""}
    assert view["investigation"] == {"engine": "cli", "model": ""}
    assert view["api"] == {"configured": False}
    assert view["can_edit"] is False
    assert [m["id"] for m in view["models"]] == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    assert ai.view(actor(repo, "dona"))["can_edit"] is True


def test_owner_updates_and_audit(make_repo):
    repo = make_repo()
    ai = _ai(repo)
    dona = actor(repo, "dona")
    view = ai.update(dona, {"radar": {"auto": False, "time": "08:30", "model": "claude-haiku-5-5"},
                            "investigation": {"model": "claude-sonnet-5-5"}})
    assert view["radar"] == {"auto": False, "time": "08:30", "engine": "cli", "model": "claude-haiku-5-5"}
    assert view["investigation"]["model"] == "claude-sonnet-5-5"
    assert ai.radar_schedule() == (False, "08:30")
    ai.update(dona, {"radar": {"auto": True}})
    assert ai.radar_schedule() == (True, "08:30")
    audits = repo.fetch("SELECT result FROM audit_log WHERE action = 'settings.ai_update'")
    assert len(audits) == 2


def test_only_owner_changes(make_repo):
    repo = make_repo()
    ai = _ai(repo)
    with pytest.raises(AuthorizationError):
        ai.update(actor(repo, "ana"), {"radar": {"auto": False}})


@pytest.mark.parametrize("payload,code", [
    ({"radar": {"time": "25:00"}}, "invalid_time"),
    ({"radar": {"auto": "sim"}}, "invalid_auto"),
    ({"radar": {"engine": "gpt"}}, "invalid_engine"),
    ({"investigation": {"model": "claude-qualquer"}}, "invalid_model"),
    ({"radar": {"engine": "api"}}, "anthropic_not_configured"),
])
def test_validation(make_repo, payload, code):
    repo = make_repo()
    ai = _ai(repo)
    with pytest.raises(SettingsError) as excinfo:
        ai.update(actor(repo, "dona"), payload)
    assert excinfo.value.code == code


def test_api_engine_needs_key_and_builds_adapter(make_repo, tmp_path):
    key_file = tmp_path / "forge_anthropic_api_key"
    key_file.write_text(KEY_PLACEHOLDER + "\n", encoding="utf-8")
    env = {"FORGE_SECRET_ANTHROPIC_API_KEY_FILE": str(key_file)}
    repo = make_repo()
    ai = _ai(repo, env=env)
    assert ai.view(actor(repo, "ana"))["api"] == {"configured": True}
    ai.update(actor(repo, "dona"), {"radar": {"engine": "api", "model": "claude-haiku-5-5"}})
    adapter = ai.adapter_for("radar")
    assert isinstance(adapter, AnthropicApiAdapter)
    assert adapter.model == "claude-haiku-5-5"
    assert adapter.effort == "low"
    key_file.unlink()
    with pytest.raises(DraftError) as excinfo:
        ai.adapter_for("radar")
    assert excinfo.value.code == "anthropic_not_configured"


def test_cli_engine_gets_model_and_readonly(make_repo, tmp_path):
    repo = make_repo()
    (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")
    env = {"PATH": "/bin", "HOME": str(tmp_path), "FORGE_CLAUDE_BIN": "claude"}
    ai = _ai(repo, env=env)
    ai.update(actor(repo, "dona"), {"radar": {"model": "claude-sonnet-5-5"}})
    adapter = ai.adapter_for("radar", env={**env})
    if isinstance(adapter, ClaudeCliAdapter):
        assert adapter.model == "claude-sonnet-5-5"
        assert adapter.permission_mode == "plan"
        assert adapter.max_turns == 2


# --- adaptador da API ---------------------------------------------------------------------------

class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _response(text="- resumo", stop_reason="end_turn", model="claude-haiku-5-5"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model=model,
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=0,
                              cache_creation_input_tokens=0),
    )


def _client(response=None, error=None):
    plain = FakeMessages(response, error)
    beta = FakeMessages(response, error)
    return SimpleNamespace(messages=plain, beta=SimpleNamespace(messages=beta)), plain, beta


def test_api_adapter_haiku_uses_plain_endpoint_and_reports_cost():
    client, plain, beta = _client(_response())
    adapter = AnthropicApiAdapter(api_key="x", model="claude-haiku-5-5", effort="low", max_tokens=2048, client=client)
    resp = adapter.complete("prompt")
    assert resp.text == "- resumo"
    assert plain.calls[0]["output_config"] == {"effort": "low"}
    assert plain.calls[0]["max_tokens"] == 2048
    assert beta.calls == []
    assert resp.usage == {"input_tokens": 1200, "output_tokens": 300, "cache_read_tokens": 0,
                          "cache_write_tokens": 0, "turns": 1, "model": "claude-haiku-5-5"}
    assert resp.cost == pytest.approx((1200 * 0.10 + 300 * 0.50) / 1_000_000)


def test_api_adapter_opus_enables_server_side_fallback():
    client, plain, beta = _client(_response(model="claude-opus-5-5"))
    AnthropicApiAdapter(api_key="x", model="claude-opus-5-5", client=client).complete("prompt")
    assert plain.calls == []
    assert beta.calls[0]["fallbacks"] == "default"
    assert beta.calls[0]["betas"] == ["server-side-fallback-2026-07-01"]


def test_api_adapter_refusal_and_errors():
    client, _plain, _beta = _client(_response(stop_reason="refusal"))
    with pytest.raises(DraftError) as excinfo:
        AnthropicApiAdapter(api_key="x", model="claude-haiku-5-5", client=client).complete("p")
    assert excinfo.value.code == "provider_refusal"
    client, _plain, _beta = _client(error=RuntimeError("falhou"))
    with pytest.raises(DraftError) as excinfo:
        AnthropicApiAdapter(api_key="x", model="claude-haiku-5-5", client=client).complete("p")
    assert excinfo.value.code == "provider_error"


def test_api_adapter_without_key_is_explicit(tmp_path):
    adapter = AnthropicApiAdapter(env={"FORGE_SECRET_ANTHROPIC_API_KEY_FILE": str(tmp_path / "nada")})
    with pytest.raises(DraftError) as excinfo:
        adapter.complete("p")
    assert excinfo.value.code == "anthropic_not_configured"


def test_key_reading_and_cost_table(tmp_path):
    missing = {"FORGE_SECRET_ANTHROPIC_API_KEY_FILE": str(tmp_path / "nada")}
    assert read_api_key(missing) == ""
    assert api_key_configured(missing) is False
    assert read_api_key({**missing, "FORGE_ANTHROPIC_API_KEY": " k "}) == "k"
    assert estimate_cost("modelo-desconhecido", {"input_tokens": 1}) is None
    assert estimate_cost("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == 24.0
