"""Adaptador Cursor CLI: pasta temporária vazia, deny documentado, sem --force/--trust/--yolo.

Risco residual aceito (ADR-015): a CLI não garante 0% de tools; deny + workspace vazio + ask.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from ..agents.provider import ProviderResponse
from ..errors import DraftError
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

FORBIDDEN_FLAGS = ("--force", "--yolo", "-f", "--trust", "--approve-mcps")
MAX_OUTPUT = 256 * 1024
DEFAULT_TIMEOUT = 120

Runner = Callable[..., subprocess.CompletedProcess]


class CursorCliAdapter:
    name = "cursor-cli"

    def __init__(self, *, agent_bin: str = "agent", model: str | None = None,
                 timeout: int = DEFAULT_TIMEOUT, env: Mapping[str, str] | None = None,
                 runner: Runner | None = None):
        self.agent_bin = agent_bin
        self.model = model
        self.timeout = timeout
        self._env = env
        self._runner = runner
        self.last_workspace: str | None = None
        self.last_argv: list[str] | None = None
        self.last_child_env: dict[str, str] | None = None

    def complete(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        workspace = tempfile.mkdtemp(prefix="forge-cursor-")
        self.last_workspace = workspace
        try:
            self._prepare_workspace(workspace)
            argv = self._argv_for(workspace, prompt)
            self.last_argv = list(argv)
            if any(f in argv for f in FORBIDDEN_FLAGS):
                raise DraftError("unsafe_flags")
            child_env = filter_env(self._env or os.environ, CURSOR_ENV_ALLOW)
            child_env["TMP"] = workspace
            child_env["TEMP"] = workspace
            child_env["TMPDIR"] = workspace
            self.last_child_env = child_env
            run = self._runner or subprocess.run
            try:
                proc = run(
                    argv, cwd=workspace, env=child_env, capture_output=True, check=False,
                    shell=False, timeout=self.timeout,
                )
            except FileNotFoundError as exc:
                raise DraftError("cursor_cli_missing") from exc
            except subprocess.TimeoutExpired as exc:
                raise DraftError("timeout") from exc
            raw = proc.stdout or b""
            if len(raw) > MAX_OUTPUT:
                raise DraftError("output_too_large")
            if proc.returncode != 0:
                raise DraftError("cursor_cli_error")
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

    def _argv_for(self, workspace: str, prompt: str) -> list[str]:
        argv = [
            self.agent_bin, "-p", "--output-format", "text", "--mode", "ask",
            "--workspace", workspace,
        ]
        if self.model:
            argv.extend(["--model", self.model])
        argv.append(prompt)
        return argv


def build_prompt(user_context: str) -> str:
    return INSTRUCTION + "\n\nCONTEXTO_DO_USUARIO:\n" + user_context + "\n"
