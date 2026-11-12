"""Escolhe o motor LLM: FORGE_ENGINE=claude|cursor (padrão claude). Fallback curto, sem segredo."""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from .claude_cli import ClaudeCliAdapter, claude_ready
from .cursor_cli import CursorCliAdapter, implementer_adapter

log = logging.getLogger("forge_core.draft")


def select_engine_adapter(
    env: Mapping[str, str] | None = None,
    *,
    implementer: bool = False,
    **kwargs,
):
    env = env or os.environ
    want = (env.get("FORGE_ENGINE") or "claude").strip().lower()
    if want not in ("claude", "cursor"):
        want = "claude"
    if want == "claude" and claude_ready(env, which=kwargs.get("which")):
        kwargs.setdefault("readonly", not implementer)
        if implementer:
            kwargs.setdefault("cleanup_workspace", False)
            kwargs.setdefault("isolate_git", True)
        return ClaudeCliAdapter(env=env, **kwargs)
    if want == "claude":
        log.info("engine result=fallback:cursor reason=unavailable")
    if implementer:
        return implementer_adapter(env=env, **kwargs)
    return CursorCliAdapter(env=env, **kwargs)
