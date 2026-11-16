"""Adaptador Claude Code CLI: `claude -p --output-format json`. Sem --dangerously-skip-permissions."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from ..agents.provider import ProviderResponse
from ..errors import DraftError
from .cursor_cli import (
    DEFAULT_TIMEOUT,
    FORBIDDEN_FLAGS,
    MAX_OUTPUT,
    SCRATCH_PREFIX,
    STDERR_SNIPPET,
    WORKSPACE_PREFIX,
    _popen_communicate,
    build_cursor_child_env,
    format_cursor_cli_error,
)

log = logging.getLogger("forge_core.draft")

SKIP_PERMISSIONS = "--dangerously-skip-permissions"
READONLY_TOOLS = "Read,Grep,Glob"
READONLY_DISALLOWED_TOOLS = "Bash,Write,Edit,WebFetch"
DEFAULT_MAX_TURNS = 8
Runner = Callable[..., subprocess.CompletedProcess]
WhichFn = Callable[[str], str | None]


def resolve_max_turns(env: Mapping[str, str], *, override: int | None = None) -> int:
    """`FORGE_CLAUDE_MAX_TURNS` (padrão 8). `override` tem precedência (ex.: Settings.claude_max_turns)."""
    if override is not None:
        return max(1, int(override))
    raw = (env.get("FORGE_CLAUDE_MAX_TURNS") or "").strip()
    if not raw:
        return DEFAULT_MAX_TURNS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_TURNS
    return value if value > 0 else DEFAULT_MAX_TURNS


def resolve_claude_bin(env: Mapping[str, str], *, which: WhichFn | None = None) -> str:
    which = which or shutil.which
    override = (env.get("FORGE_CLAUDE_BIN") or "").strip()
    if override:
        return override
    found = which("claude")
    if found:
        return found
    raise DraftError("claude_cli_missing")


def claude_login_present(env: Mapping[str, str], *, home: Path | None = None) -> bool:
    root = home if home is not None else Path(env.get("HOME") or "")
    if not root:
        return False
    for path in (
        root / ".claude.json",
        root / ".claude" / ".credentials.json",
        root / ".claude" / "credentials.json",
    ):
        try:
            if path.is_file() and not path.is_symlink():
                return True
        except OSError:
            continue
    return False


def parse_claude_result(raw: bytes) -> str:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DraftError("claude_cli_error") from exc
    if not isinstance(data, dict):
        raise DraftError("claude_cli_error")
    if data.get("is_error") is True:
        raise DraftError("claude_cli_error")
    text = data.get("result")
    if not isinstance(text, str):
        raise DraftError("claude_cli_error")
    return text


def _int_or_none(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_claude_usage(raw: bytes) -> tuple[dict, float | None]:
    """Uso da chamada a partir do JSON do `claude -p`. Nunca levanta: sem dado, devolve vazio.

    O custo vem de `total_cost_usd`, que o CLI calcula a preço de lista da API
    (`costBasis: "list"`). Com assinatura, é uma estimativa, não uma cobrança.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, None
    if not isinstance(data, dict):
        return {}, None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    models = data.get("modelUsage") if isinstance(data.get("modelUsage"), dict) else {}
    out = {
        "input_tokens": _int_or_none(usage.get("input_tokens")),
        "output_tokens": _int_or_none(usage.get("output_tokens")),
        "cache_read_tokens": _int_or_none(usage.get("cache_read_input_tokens")),
        "cache_write_tokens": _int_or_none(usage.get("cache_creation_input_tokens")),
        "turns": _int_or_none(data.get("num_turns")),
        "model": ", ".join(sorted(str(k) for k in models))[:120],
    }
    cost = data.get("total_cost_usd")
    try:
        cost_value = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_value = None
    return {k: v for k, v in out.items() if v not in (None, "")}, cost_value


class ClaudeCliAdapter:
    name = "claude-cli"

    def __init__(
        self,
        *,
        agent_bin: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        env: Mapping[str, str] | None = None,
        runner: Runner | None = None,
        which: WhichFn | None = None,
        platform: str | None = None,
        workspace: str | None = None,
        cleanup_workspace: bool = True,
        isolate_git: bool = False,
        readonly: bool = True,
        model: str | None = None,
        max_turns: int | None = None,
        permission_mode: str | None = None,
        disallowed_tools: str | None = None,
        **_ignored,
    ):
        self.agent_bin = agent_bin
        self.timeout = timeout
        self._env = env
        self._runner = runner
        self._which = which
        self._platform = platform
        self.workspace = workspace
        self.cleanup_workspace = cleanup_workspace
        self.isolate_git = isolate_git
        self.readonly = readonly
        self.model = model
        self.max_turns = max_turns
        self.permission_mode = permission_mode
        self.disallowed_tools = disallowed_tools
        self.last_workspace: str | None = None
        self.last_argv: list[str] | None = None
        self.last_child_env: dict[str, str] | None = None

    def complete(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        env = self._env or os.environ
        platform = self._platform if self._platform is not None else sys.platform
        agent_bin = self.agent_bin or resolve_claude_bin(env, which=self._which)
        owned = self.workspace
        if owned:
            workspace = str(Path(owned))
            self.last_workspace = workspace
        else:
            workspace = tempfile.mkdtemp(prefix=WORKSPACE_PREFIX)
            self.last_workspace = workspace
        scratch = tempfile.mkdtemp(prefix=SCRATCH_PREFIX)
        try:
            argv = self._argv_for(agent_bin, env)
            self.last_argv = list(argv)
            if SKIP_PERMISSIONS in argv or any(f in argv for f in FORBIDDEN_FLAGS):
                raise DraftError("unsafe_flags")
            child_env = build_cursor_child_env(
                env, platform=platform, scratch_tmp=scratch, isolate_git=self.isolate_git,
            )
            if "ANTHROPIC_API_KEY" in child_env or "ANTHROPIC_AUTH_TOKEN" in child_env:
                raise DraftError("unsafe_flags")
            if Path(child_env.get("TMP", scratch)).resolve() == Path(workspace).resolve():
                raise DraftError("unsafe_flags")
            self.last_child_env = child_env
            run = self._runner or _popen_communicate
            try:
                proc = run(
                    argv, cwd=workspace, env=child_env, capture_output=True, check=False,
                    shell=False, timeout=self.timeout, input=prompt.encode("utf-8"),
                )
            except FileNotFoundError as exc:
                raise DraftError("claude_cli_missing") from exc
            except subprocess.TimeoutExpired as exc:
                raise DraftError("timeout") from exc
            raw = proc.stdout or b""
            if len(raw) > MAX_OUTPUT:
                raise DraftError("output_too_large")
            if proc.returncode != 0:
                hint = format_cursor_cli_error(
                    proc.returncode, proc.stderr or b"", child_env, stdout=raw,
                )
                raise DraftError("claude_cli_error", hint[:STDERR_SNIPPET])
            text = parse_claude_result(raw)
            usage, cost = parse_claude_usage(raw)
            return ProviderResponse(text=text, usage=usage, cost=cost)
        finally:
            if self.cleanup_workspace and owned is None:
                shutil.rmtree(workspace, ignore_errors=True)
            shutil.rmtree(scratch, ignore_errors=True)

    def _argv_for(self, agent_bin: str, env: Mapping[str, str]) -> list[str]:
        argv = [agent_bin, "-p", "--output-format", "json"]
        if self.readonly:
            argv.extend(["--allowedTools", READONLY_TOOLS])
        if self.permission_mode:
            argv.extend(["--permission-mode", self.permission_mode])
        if self.disallowed_tools:
            argv.extend(["--disallowedTools", self.disallowed_tools])
        if self.model:
            argv.extend(["--model", self.model])
        argv.extend(["--max-turns", str(resolve_max_turns(env, override=self.max_turns))])
        if SKIP_PERMISSIONS in argv:
            raise DraftError("unsafe_flags")
        return argv


def claude_ready(env: Mapping[str, str], *, which: WhichFn | None = None) -> bool:
    try:
        resolve_claude_bin(env, which=which)
    except DraftError:
        return False
    return claude_login_present(env)
