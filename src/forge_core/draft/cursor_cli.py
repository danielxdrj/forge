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
from .envfilter import assert_no_host_secrets, cursor_env_allow, filter_env
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
SCRATCH_PREFIX = "forge-cursor-scratch-"
MAX_OUTPUT = 256 * 1024
STDERR_SNIPPET = 500
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_OLD_SPACE_MB = 512
MIN_MAX_OLD_SPACE_MB = 256
MAX_MAX_OLD_SPACE_MB = 4096
_SENSITIVE_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "SENHA", "KEY", "AUTH")

Runner = Callable[..., subprocess.CompletedProcess]
WhichFn = Callable[[str], str | None]
ExistsFn = Callable[[str], bool]


def resolve_cursor_model(env: Mapping[str, str], *, flag: str | None = None) -> str | None:
    """Precedência compartilhada por draft e doctor: flag CLI > FORGE_CURSOR_MODEL > padrão da CLI."""
    for raw in (flag, env.get("FORGE_CURSOR_MODEL")):
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


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


def max_old_space_mb(env: Mapping[str, str]) -> int:
    raw = (env.get("FORGE_CURSOR_MAX_OLD_SPACE_MB") or str(DEFAULT_MAX_OLD_SPACE_MB)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_OLD_SPACE_MB
    if value < MIN_MAX_OLD_SPACE_MB or value > MAX_MAX_OLD_SPACE_MB:
        return DEFAULT_MAX_OLD_SPACE_MB
    return value


def forge_node_options(env: Mapping[str, str]) -> str:
    """NODE_OPTIONS gerado pelo Forge. Não reenvia o NODE_OPTIONS do usuário."""
    return f"--max-old-space-size={max_old_space_mb(env)}"


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


def format_cursor_cli_error(
    returncode: int,
    stderr: bytes | str,
    env: Mapping[str, str] | None = None,
    stdout: bytes | str = b"",
) -> str:
    def _txt(raw: bytes | str) -> str:
        return raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")

    text = _txt(stderr)
    if not text.strip():
        text = _txt(stdout)
    text = redact(text)
    for secret in _sensitive_env_values(env):
        if secret:
            text = text.replace(secret, "***")
    snippet = text[:STDERR_SNIPPET]
    return f"exit={returncode} stderr={snippet}"


def build_cursor_child_env(
    src: Mapping[str, str],
    *,
    platform: str,
    scratch_tmp: str | None = None,
) -> dict[str, str]:
    child = filter_env(src, cursor_env_allow(platform))
    child["NODE_OPTIONS"] = forge_node_options(src)
    has_tmp = any(k.upper() in ("TMP", "TEMP", "TMPDIR") for k in child)
    if not has_tmp and scratch_tmp:
        child["TMP"] = scratch_tmp
        child["TEMP"] = scratch_tmp
        child["TMPDIR"] = scratch_tmp
    assert_no_host_secrets(child)
    if any(k.upper().startswith("FORGE_") for k in child):
        raise DraftError("unsafe_flags")
    return child


def _popen_communicate(argv, cwd=None, env=None, timeout=None, input=None, **_kwargs):
    with subprocess.Popen(
        argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, shell=False,
    ) as proc:
        try:
            out, err = proc.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        return subprocess.CompletedProcess(argv, proc.returncode, out, err)


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
        self.last_scratch: str | None = None
        self.last_argv: list[str] | None = None
        self.last_child_env: dict[str, str] | None = None
        self.last_stdin: bytes | None = None
        self.last_stdin_eof: bool = False
        self.last_resolved_bin: str | None = None

    def complete(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        env = self._env or os.environ
        platform = self._platform if self._platform is not None else sys.platform
        agent_bin = self.agent_bin or resolve_agent_executable(
            env, which=self._which, path_exists=self._path_exists, platform=platform,
        )
        self.last_resolved_bin = agent_bin
        workspace = tempfile.mkdtemp(prefix=WORKSPACE_PREFIX)
        scratch = tempfile.mkdtemp(prefix=SCRATCH_PREFIX)
        self.last_workspace = workspace
        self.last_scratch = scratch
        try:
            self._prepare_workspace(workspace)
            argv = self._argv_for(workspace, agent_bin)
            self.last_argv = list(argv)
            if any(f in argv for f in FORBIDDEN_FLAGS):
                raise DraftError("unsafe_flags")
            if TRUST_FLAG in argv and not is_owned_forge_workspace(workspace, self.last_workspace):
                raise DraftError("unsafe_flags")
            child_env = build_cursor_child_env(env, platform=platform, scratch_tmp=scratch)
            if Path(child_env.get("TMP", scratch)).resolve() == Path(workspace).resolve():
                raise DraftError("unsafe_flags")
            self.last_child_env = child_env
            payload = prompt.encode("utf-8")
            self.last_stdin = payload
            run = self._runner or _popen_communicate
            try:
                proc = run(
                    argv, cwd=workspace, env=child_env, capture_output=True, check=False,
                    shell=False, timeout=self.timeout, input=payload,
                )
            except FileNotFoundError as exc:
                raise DraftError("cursor_cli_missing") from exc
            except subprocess.TimeoutExpired as exc:
                raise DraftError("timeout") from exc
            self.last_stdin_eof = True
            raw = proc.stdout or b""
            if len(raw) > MAX_OUTPUT:
                raise DraftError("output_too_large")
            if proc.returncode != 0:
                hint = format_cursor_cli_error(
                    proc.returncode, proc.stderr or b"", child_env, stdout=raw,
                )
                raise DraftError("cursor_cli_error", hint)
            return ProviderResponse(text=raw.decode("utf-8", "replace"))
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
            shutil.rmtree(scratch, ignore_errors=True)

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


def diagnose_cursor_cli(
    env: Mapping[str, str],
    *,
    out,
    runner: Runner | None = None,
    which: WhichFn | None = None,
    path_exists: ExistsFn | None = None,
    platform: str | None = None,
    timeout: int = 60,
    model_flag: str | None = None,
) -> int:
    """Diagnóstico: nomes de env, caminhos, `agent --version` e uma chamada mínima. Sem valores secretos."""
    platform = sys.platform if platform is None else platform
    try:
        agent = resolve_agent_executable(env, which=which, path_exists=path_exists, platform=platform)
    except DraftError as exc:
        print(f"agent: {exc.code}", file=out)
        return 1
    print(f"agent_path: {agent}", file=out)
    scratch = tempfile.mkdtemp(prefix=SCRATCH_PREFIX)
    try:
        child = build_cursor_child_env(env, platform=platform, scratch_tmp=scratch)
        print("env_names: " + ",".join(sorted(child)), file=out)
        print(f"scratch_tmp: {scratch}", file=out)
        print("workspace: mkdtemp forge-cursor- (criado só na chamada mínima)", file=out)
        print("node_options: " + child.get("NODE_OPTIONS", ""), file=out)
        run = runner or _popen_communicate
        try:
            ver = run(
                [agent, "--version"], cwd=scratch, env=child, capture_output=True,
                check=False, shell=False, timeout=timeout, input=b"",
            )
        except FileNotFoundError:
            print("version: cursor_cli_missing", file=out)
            return 1
        vtext = (ver.stdout or b"").decode("utf-8", "replace").strip()
        print(f"version_exit: {ver.returncode}", file=out)
        print(f"version: {redact(vtext)[:200]}", file=out)
        model = resolve_cursor_model(env, flag=model_flag)
        print("model=" + (model if model else "(padrão da CLI)"), file=out)
        adapter = CursorCliAdapter(
            agent_bin=agent, env=env, runner=runner, which=which,
            path_exists=path_exists, platform=platform, timeout=timeout, model=model,
        )
        try:
            resp = adapter.complete("responda OK")
            print("probe_exit: 0", file=out)
            print("probe_text: " + redact(resp.text)[:200], file=out)
            return 0
        except DraftError as exc:
            print(f"probe_error: {exc}", file=out)
            return 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
