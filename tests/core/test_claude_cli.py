"""Adaptador Claude Code: subprocesso falso, sem rede, sem chave."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from forge_core.draft.claude_cli import (
    READONLY_DISALLOWED_TOOLS,
    ClaudeCliAdapter,
    parse_claude_result,
    resolve_max_turns,
)
from forge_core.draft.engine import select_engine_adapter
from forge_core.errors import DraftError


def _runner(payload, *, code=0, stderr=b""):
    captured = {}

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env") or {}
        captured["cwd"] = kwargs.get("cwd")
        captured["input"] = kwargs.get("input")
        body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
        return subprocess.CompletedProcess(argv, code, body, stderr)

    return run, captured


def test_claude_cli_parses_result_readonly_tools_no_api_key(tmp_path):
    run, captured = _runner({"type": "result", "result": "rascunho ok", "is_error": False})
    env = {
        "PATH": "/bin",
        "HOME": str(tmp_path),
        "ANTHROPIC_API_KEY": "sk-ant-SECRET-nao-copiar",
        "GH_TOKEN": "gho_SECRET",
    }
    adapter = ClaudeCliAdapter(
        agent_bin="claude", runner=run, env=env, platform="linux", readonly=True,
    )
    resp = adapter.complete("contexto do utilizador")
    assert resp.text == "rascunho ok"
    argv = captured["argv"]
    assert argv[:4] == ["claude", "-p", "--output-format", "json"]
    assert "--allowedTools" in argv
    assert "Read,Grep,Glob" in argv
    assert "--dangerously-skip-permissions" not in argv
    child = captured["env"]
    assert "ANTHROPIC_API_KEY" not in child
    assert "GH_TOKEN" not in child
    assert "FORGE_ENGINE" not in child
    assert captured["input"] == b"contexto do utilizador"


def test_claude_cli_implementer_writes_in_cwd_never_skips(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    run, captured = _runner({"result": "diff aplicado"})
    adapter = ClaudeCliAdapter(
        agent_bin="claude", runner=run, env={"PATH": "/bin", "HOME": str(tmp_path)},
        platform="linux", readonly=False, workspace=str(clone), cleanup_workspace=False,
        isolate_git=True,
    )
    resp = adapter.complete("implemente")
    assert resp.text == "diff aplicado"
    assert captured["cwd"] == str(clone)
    assert "--allowedTools" not in captured["argv"]
    assert "--dangerously-skip-permissions" not in captured["argv"]


def test_parse_claude_result_rejects_error_payload():
    try:
        parse_claude_result(json.dumps({"result": "x", "is_error": True}).encode())
        assert False
    except DraftError as exc:
        assert exc.code == "claude_cli_error"


def test_select_engine_falls_back_to_cursor_when_claude_missing(tmp_path):
    adapter = select_engine_adapter(
        {"PATH": "/bin", "HOME": str(tmp_path), "FORGE_ENGINE": "claude"},
        which=lambda _name: None,
        agent_bin="agent",
    )
    assert adapter.name == "cursor-cli"


def test_claude_cli_default_max_turns_eight(tmp_path):
    run, captured = _runner({"result": "ok"})
    adapter = ClaudeCliAdapter(
        agent_bin="claude", runner=run, env={"PATH": "/bin", "HOME": str(tmp_path)},
        platform="linux", readonly=True,
    )
    adapter.complete("contexto")
    argv = captured["argv"]
    assert "--max-turns" in argv
    assert argv[argv.index("--max-turns") + 1] == "8"


def test_claude_cli_max_turns_env_override(tmp_path):
    run, captured = _runner({"result": "ok"})
    adapter = ClaudeCliAdapter(
        agent_bin="claude", runner=run,
        env={"PATH": "/bin", "HOME": str(tmp_path), "FORGE_CLAUDE_MAX_TURNS": "3"},
        platform="linux", readonly=True,
    )
    adapter.complete("contexto")
    argv = captured["argv"]
    assert argv[argv.index("--max-turns") + 1] == "3"


def test_claude_cli_explicit_max_turns_wins_over_env(tmp_path):
    run, captured = _runner({"result": "ok"})
    adapter = ClaudeCliAdapter(
        agent_bin="claude", runner=run,
        env={"PATH": "/bin", "HOME": str(tmp_path), "FORGE_CLAUDE_MAX_TURNS": "3"},
        platform="linux", readonly=True, max_turns=12,
    )
    adapter.complete("contexto")
    argv = captured["argv"]
    assert argv[argv.index("--max-turns") + 1] == "12"


def test_resolve_max_turns_invalid_env_falls_back_to_default():
    assert resolve_max_turns({"FORGE_CLAUDE_MAX_TURNS": "nao-numero"}) == 8
    assert resolve_max_turns({}) == 8
    assert resolve_max_turns({"FORGE_CLAUDE_MAX_TURNS": "0"}) == 8


def test_claude_cli_investigation_mode_sets_plan_and_disallowed_tools(tmp_path):
    run, captured = _runner({"result": "achado"})
    adapter = ClaudeCliAdapter(
        agent_bin="claude", runner=run, env={"PATH": "/bin", "HOME": str(tmp_path)},
        platform="linux", readonly=True, permission_mode="plan",
        disallowed_tools=READONLY_DISALLOWED_TOOLS,
    )
    adapter.complete("investigue isto")
    argv = captured["argv"]
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "--disallowedTools" in argv
    assert argv[argv.index("--disallowedTools") + 1] == "Bash,Write,Edit,WebFetch"
    assert "--allowedTools" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_select_engine_uses_claude_when_logged_in(tmp_path):
    cred = Path(tmp_path) / ".claude"
    cred.mkdir()
    (cred / ".credentials.json").write_text("{}", encoding="utf-8")
    adapter = select_engine_adapter(
        {"PATH": "/bin", "HOME": str(tmp_path), "FORGE_ENGINE": "claude", "FORGE_CLAUDE_BIN": "claude"},
        which=lambda name: "/usr/local/bin/claude" if name == "claude" else None,
    )
    assert adapter.name == "claude-cli"
    assert adapter.readonly is True
