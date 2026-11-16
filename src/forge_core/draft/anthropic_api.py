"""Motor pela API da Anthropic (SDK oficial `anthropic`). Desligado até existir a chave.

A chave nunca vem do Git nem fica no ambiente do processo: o entrypoint grava
`FORGE_ANTHROPIC_API_KEY` em `/run/secrets/forge_anthropic_api_key` (0600, tmpfs) e remove
a variável antes do uvicorn. Aqui só se lê o arquivo (ou a variável, em dev/teste).

Vantagem sobre o Claude Code CLI: a chamada leva só o pedido. Não há o prompt de sistema
e as ferramentas da CLI (~25 mil tokens de cache por chamada).

O custo devolvido é estimado a preço de lista (tabela abaixo, US$ por milhão de tokens).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from ..agents.provider import ProviderResponse
from ..errors import DraftError

SECRET_FILE_ENV = "FORGE_SECRET_ANTHROPIC_API_KEY_FILE"
DEFAULT_SECRET_FILE = "/run/secrets/forge_anthropic_api_key"
KEY_ENV = "FORGE_ANTHROPIC_API_KEY"
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_TIMEOUT = 120
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# US$ por 1M tokens: entrada, saída, leitura de cache, gravação de cache (5 min = 1,25 x entrada).
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
# Modelos com fallback no servidor quando o modelo recusa o pedido (Haiku 5.5 não tem).
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})


def read_api_key(env: Mapping[str, str] | None = None) -> str:
    """Chave da API, ou "" se não configurada. Nunca registra o valor."""
    env = env if env is not None else os.environ
    path = Path(env.get(SECRET_FILE_ENV) or DEFAULT_SECRET_FILE)
    try:
        if path.is_file() and not path.is_symlink():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    except OSError:
        pass
    return (env.get(KEY_ENV) or "").strip()


def api_key_configured(env: Mapping[str, str] | None = None) -> bool:
    return bool(read_api_key(env))


def estimate_cost(model: str, usage: dict) -> float | None:
    prices = PRICES.get(model)
    if prices is None:
        return None
    p_in, p_out, p_cr, p_cw = prices
    total = (
        (usage.get("input_tokens") or 0) * p_in
        + (usage.get("output_tokens") or 0) * p_out
        + (usage.get("cache_read_tokens") or 0) * p_cr
        + (usage.get("cache_write_tokens") or 0) * p_cw
    )
    return round(total / 1_000_000, 6)


class AnthropicApiAdapter:
    name = "anthropic-api"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        effort: str = "medium",
        timeout: int = DEFAULT_TIMEOUT,
        env: Mapping[str, str] | None = None,
        client=None,
    ):
        self._api_key = api_key if api_key is not None else read_api_key(env)
        self.model = (model or DEFAULT_MODEL).strip()
        self.max_tokens = max_tokens
        self.effort = effort
        self.timeout = timeout
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise DraftError("anthropic_not_configured")
        try:
            import anthropic
        except ImportError as exc:
            raise DraftError("anthropic_sdk_missing") from exc
        self._client = anthropic.Anthropic(api_key=self._api_key, timeout=float(self.timeout), max_retries=2)
        return self._client

    def complete(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        client = self._get_client()
        kwargs = {
            "model": self.model,
            "max_tokens": int(max_tokens or self.max_tokens),
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": self.effort},
        }
        try:
            if self.model in FALLBACK_MODELS:
                response = client.beta.messages.create(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")
            else:
                response = client.messages.create(**kwargs)
        except Exception as exc:  # traduz os erros tipados do SDK para códigos fixos, sem segredo
            raise DraftError(_error_code(exc)) from exc
        if getattr(response, "stop_reason", None) == "refusal":
            raise DraftError("provider_refusal")
        text = "".join(
            getattr(block, "text", "") for block in (response.content or []) if getattr(block, "type", "") == "text"
        ).strip()
        raw = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(raw, "input_tokens", None),
            "output_tokens": getattr(raw, "output_tokens", None),
            "cache_read_tokens": getattr(raw, "cache_read_input_tokens", None),
            "cache_write_tokens": getattr(raw, "cache_creation_input_tokens", None),
            "turns": 1,
            "model": str(getattr(response, "model", "") or self.model),
        }
        usage = {k: v for k, v in usage.items() if v is not None}
        return ProviderResponse(text=text, usage=usage, cost=estimate_cost(usage.get("model", self.model), usage))


def _error_code(exc: Exception) -> str:
    try:
        import anthropic
    except ImportError:
        return "provider_error"
    if isinstance(exc, anthropic.AuthenticationError):
        return "anthropic_auth"
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "anthropic_forbidden"
    if isinstance(exc, anthropic.RateLimitError):
        return "anthropic_rate_limit"
    if isinstance(exc, anthropic.NotFoundError):
        return "anthropic_model_not_found"
    if isinstance(exc, anthropic.APITimeoutError):
        return "timeout"
    if isinstance(exc, anthropic.APIConnectionError):
        return "provider_unreachable"
    if isinstance(exc, anthropic.APIStatusError):
        return "provider_error"
    return "provider_error"
