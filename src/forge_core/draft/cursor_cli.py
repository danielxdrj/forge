"""Adaptador Cursor CLI: pasta temporária vazia, deny documentado, prompt via stdin.

Risco residual aceito (ADR-015): a CLI não garante 0% de tools; deny + workspace vazio + ask.
`--trust` só no diretório temporário que o Forge cria e apaga nesta chamada.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path, PureWindowsPath

from ..agents.provider import ProviderResponse
from ..errors import DraftError
from ..logging import redact
from .envfilter import CURSOR_ENV_ALLOW, filter_env
from .template import INSTRUCTION

# https://cursor.com/docs/cli/reference/permissions
# Glob * / ** / *:* como a página documenta. Shell() e Read() vazios NÃO são usados.
DOCUMENTED_DENY = (
    "Shell(*)",
    "Shell(*:*)",
    "Read(*)",
    "Read(**/*)",
    "Read(/**)",
    "Write(*)",
    "Write(**/*)",
    "Write(/**)",
    "WebFetch(*)",
    "Mcp(*:*)",
)

FORBIDDEN_FLAGS = ("--force", "--yolo", "-f", "--approve-mcps")
TRUST_FLAG = "--trust"
WORKSPACE_PREFIX = "forge-cursor-"
MAX_OUTPUT = 256 * 1024
STDERR_SNIPPET = 500
DEFAULT_TIMEOUT = 120
_SENSITIVE_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "SENHA", "KEY", "AUTH")

Runner = Callable[..., subprocess.CompletedProcess]
WhichFn = Callable[[str], str | None]
ExistsFn = Callable[[str], bool]


def resolve_agent_executable(
    env: Mapping[str, str],
    *,
    which: WhichFn | None = None,
    path_exists: ExistsFn | None = None,
    platform: str | None = None,
) -> str:
    """FORGE_CURSOR_AGENT > shutil.which('agent') (PATHEXT no Windows) > %LOCALAPPDATA%\\cursor-agent\\agent.cmd."""
    which = which or shutil.which
    path_exists = path_exists or os.path.isfile
    platform = sys.platform if platform is None else platform
    override = (env.get("FORGE_CURSOR_AGENT") or "").strip()
    if override:
        return override
    found = which("agent")
    if found:
        return found
    if platform == "win32":
        local = (env.get("LOCALAPPDATA") or "").strip()
        if local:
            candidate = str(PureWindowsPath(local) / "cursor-agent" / "agent.cmd")
            if path_exists(candidate):
                return candidate
    raise DraftError("cursor_cli_missing")


def is_owned_forge_workspace(cwd: str, owned: str | None) -> bool:
    if not cwd or not owned:
        return False
    try:
        return Path(cwd).resolve() == Path(owned).resolve()
    except OSError:
        return False


def _sensitive_env_values(env: Mapping[str, str] | None) -> tuple[str, ...]:
    if not env:
        return ()
    out = []
    for key, value in env.items():
        if not value:
            continue
        upper = key.upper()
        if any(m in upper for m in _SENSITIVE_ENV_MARKERS):
            out.append(value)
    return tuple(out)


def format_cursor_cli_error(returncode: int, stderr: bytes | str, env: Mapping[str, str] | None = None) -> str:
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr or "")
    text = redact(text)
    for secret in _sensitive_env_values(env):
        if secret:
            text = text.replace(secret, "***")
    snippet = text[:STDERR_SNIPPET]
    return f"exit={returncode} stderr={snippet}"


class CursorCliAdapter:
    name = "cursor-cli"

    def __init__(self, *, agent_bin: str | None = None, model: str | None = None,
                 timeout: int = DEFAULT_TIMEOUT, env: Mapping[str, str] | None = None,
                 runner: Runner | None = None, which: WhichFn | None = None,
                 path_exists: ExistsFn | None = None, platform: str | None = None):
        self.agent_bin = agent_bin
        self.model = model
        self.timeout = timeout
        self._env = env
        self._runner = runner
        self._which = which
        self._path_exists = path_exists
        self._platform = platform
        self.last_workspace: str | None = None
        self.last_argv: list[str] | None = None
        self.last_child_env: dict[str, str] | None = None
        self.last_stdin: bytes | None = None
        self.last_resolved_bin: str | None = None

    def complete(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        env = self._env or os.environ
        agent_bin = self.agent_bin or resolve_agent_executable(
            env, which=self._which, path_exists=self._path_exists, platform=self._platform,
        )
        self.last_resolved_bin = agent_bin
        workspace = tempfile.mkdtemp(prefix=WORKSPACE_PREFIX)
        self.last_workspace = workspace
        try:
            self._prepare_workspace(workspace)
            argv = self._argv_for(workspace, agent_bin)
            self.last_argv = list(argv)
            if any(f in argv for f in FORBIDDEN_FLAGS):
                raise DraftError("unsafe_flags")
            if TRUST_FLAG in argv and not is_owned_forge_workspace(workspace, self.last_workspace):
                raise DraftError("unsafe_flags")
            child_env = filter_env(env, CURSOR_ENV_ALLOW)
            child_env["TMP"] = workspace
            child_env["TEMP"] = workspace
            child_env["TMPDIR"] = workspace
            self.last_child_env = child_env
            payload = prompt.encode("utf-8")
            self.last_stdin = payload
            run = self._runner or subprocess.run
            try:
                proc = run(
                    argv, cwd=workspace, env=child_env, capture_output=True, check=False,
                    shell=False, timeout=self.timeout, input=payload,
                )
            except FileNotFoundError as exc:
                raise DraftError("cursor_cli_missing") from exc
            except subprocess.TimeoutExpired as exc:
                raise DraftError("timeout") from exc
            raw = proc.stdout or b""
            if len(raw) > MAX_OUTPUT:
                raise DraftError("output_too_large")
            if proc.returncode != 0:
                hint = format_cursor_cli_error(proc.returncode, proc.stderr or b"", child_env)
                raise DraftError("cursor_cli_error", hint)
            return ProviderResponse(text=raw.decode("utf-8", "replace"))
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _prepare_workspace(self, workspace: str) -> None:
        cursor_dir = Path(workspace) / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "cli.json").write_text(
            json.dumps({"permissions": {"allow": [], "deny": list(DOCUMENTED_DENY)}}, indent=2),
            encoding="utf-8",
        )
        leftovers = [p.name for p in Path(workspace).iterdir() if p.name != ".cursor"]
        if leftovers:
            raise DraftError("workspace_not_empty")

    def _argv_for(self, workspace: str, agent_bin: str | None = None) -> list[str]:
        bin_path = agent_bin or self.last_resolved_bin or self.agent_bin or "agent"
        argv = [
            bin_path, "-p", "--output-format", "text", "--mode", "ask",
            "--workspace", workspace,
        ]
        if self.model:
            argv.extend(["--model", self.model])
        if is_owned_forge_workspace(workspace, self.last_workspace):
            argv.append(TRUST_FLAG)
        return argv


def build_prompt(user_context: str) -> str:
    return INSTRUCTION + "\n\nCONTEXTO_DO_USUARIO:\n" + user_context + "\n"
