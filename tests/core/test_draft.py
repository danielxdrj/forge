"""Rascunho de issue: LLM falso, gh falso fiel ao CLI real. Sem rede."""
from __future__ import annotations

import json
import subprocess
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from auth_helpers import FakeGitHub, TEST_CLIENT_ID, bootstrap, person
from forge_core.auth import cli as auth_cli
from forge_core.agents.provider import ProviderResponse
from forge_core.draft.cli import run as draft_run
from forge_core.draft.context import MAX_CONTEXT_BYTES, FileContext, TextContext, resolve_source
from forge_core.draft.cursor_cli import (
    DOCUMENTED_DENY,
    FORBIDDEN_FLAGS,
    STDERR_SNIPPET,
    TRUST_FLAG,
    CursorCliAdapter,
    diagnose_cursor_cli,
    format_cursor_cli_error,
    forge_node_options,
    resolve_agent_executable,
    resolve_cursor_model,
)
from forge_core.draft.envfilter import (
    CURSOR_ENV_ALLOW_WIN,
    GH_ENV_ALLOW,
    cursor_env_allow,
    filter_env,
)
from forge_core.draft.github_gh import GhCli, match_option, names_match
from forge_core.draft.service import DraftService, ask_confirm, parse_remote, sidecar_path
from forge_core.draft.template import (
    ASSIGNEE, PENDING, SUGGESTION_PREFIX, fill_inferred_sections, parse_model_json,
    render, required_pending, validate_repo,
)
from forge_core.errors import DraftError
from forge_core.storage import open_repository
from forge_core.tasks import TaskService

VALID = {
    "title": "fix: login recusa senha valida",
    "solicitado_por": "Ana",
    "objetivo": "Corrigir o login.",
    "contexto": "Tela de autenticacao.",
    "problemas": ["Senha valida e recusada"],
    "novos_problemas": "",
    "situacao_atual": "O botao entra e volta erro.",
    "comportamento_esperado": ["Aceitar senha valida"],
    "criterios": ["Teste de login passa"],
    "observacoes": ["So o modulo de login"],
}

GRAPHQL_FIELDS = {
    "data": {
        "node": {
            "fields": {
                "nodes": [
                    {
                        "id": "f-s", "name": "Sprint",
                        "configuration": {
                            "iterations": [
                                {"id": "it-now", "title": "Semana 45",
                                 "startDate": "2026-11-03", "duration": 21},
                            ],
                            "completedIterations": [],
                        },
                    },
                    {"id": "f-t", "name": "Tipo", "options": [{"id": "o-bug", "name": "Bug"}]},
                    {"id": "f-p", "name": "Prioridade", "options": [{"id": "o-high", "name": "🔴 Alta"}]},
                    {"id": "f-z", "name": "Size", "options": [{"id": "o-3", "name": "3"}]},
                ]
            }
        }
    }
}

# field-list real: tipo, sem iterations (cli/cli#11068)
FIELD_LIST_REAL = {
    "fields": [
        {"id": "f-s", "name": "Sprint", "type": "ProjectV2IterationField"},
        {"id": "f-t", "name": "Tipo", "type": "ProjectV2SingleSelectField"},
    ]
}

META = {"tipo": "Bug", "prioridade": "Alta", "size": "3", "sprint": "", "escopo": ""}
TITLE = VALID["title"]
ISSUE_URL = "https://github.com/acme/app/issues/9"


class _Buf:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass


class FakeLLM:
    name = "fake"

    def __init__(self, text=None, err=None):
        self.text = text if text is not None else json.dumps(VALID)
        self.err = err
        self.prompts = []

    def complete(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        if self.err:
            raise self.err
        return ProviderResponse(text=self.text)


def _people(tmp_path):
    repo = open_repository(f"sqlite:///{tmp_path / 'd.db'}")
    gh = FakeGitHub()
    owner = bootstrap(repo, gh)
    editor = person(repo, owner, gh, "ana", 1001, "editor")
    viewer = person(repo, owner, gh, "solta", 1004)
    return repo, gh, owner, editor, viewer


def _env(tmp_path):
    return {
        "FORGE_CONFIG_DIR": str(tmp_path / "cfg"),
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'd.db'}",
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
        "FORGE_CURSOR_MODEL": "<MODELO_DA_ASSINATURA>",
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home" / ".config"),
    }


def test_template_order_and_pending_and_no_scope():
    data = parse_model_json(json.dumps(VALID))
    body = render(data)
    order = ["## Solicitado Por", "## Objetivo", "## Contexto",
             "## Foram reportados os seguintes problemas:",
             "## Situação Atual", "## Comportamento Esperado", "## Critérios de Aceite",
             "## Observações"]
    positions = [body.index(h) for h in order]
    assert positions == sorted(positions)
    assert "\n## Solicitado Por\n\n- Ana\n" in body
    assert "Escopo" not in body
    incomplete = dict(VALID, solicitado_por="Descreva o objetivo da solicitação aqui")
    parsed = parse_model_json(json.dumps(incomplete))
    assert parsed["solicitado_por"] == PENDING
    with pytest.raises(DraftError) as ei:
        parse_model_json(json.dumps(dict(VALID, objetivo="ok\n## Escopo\nnao")))
    assert ei.value.code == "scope_in_body"
    with pytest.raises(DraftError) as ei:
        parse_model_json(json.dumps(dict(VALID, observacoes=["pendência de escopo do Forge"])))
    assert ei.value.code == "scope_in_body"
    ok_ctx = parse_model_json(json.dumps(dict(
        VALID,
        contexto="ajustar o escopo do relatorio",
        observacoes=["fora do escopo desta sprint"],
    )))
    assert "escopo do relatorio" in ok_ctx["contexto"]
    assert "escopo desta sprint" in ok_ctx["observacoes"][0]
    with pytest.raises(DraftError) as ei:
        parse_model_json(json.dumps(dict(VALID, situacao_atual="Escopo:\nainda vazio")))
    assert ei.value.code == "scope_in_body"
    with pytest.raises(DraftError) as ei:
        parse_model_json(json.dumps(dict(VALID, criterios=["definir o escopo operacional"])))
    assert ei.value.code == "scope_in_body"
    with pytest.raises(DraftError) as ei:
        parse_model_json(json.dumps(dict(VALID, observacoes=["falta a configuração do Forge"])))
    assert ei.value.code == "scope_in_body"


def test_any_pending_marker_blocks_remote():
    mixed = parse_model_json(json.dumps(dict(VALID, criterios=["Teste passa", "[PENDENTE]"])))
    assert mixed["criterios"] == ["Teste passa"]
    assert "criterios" not in required_pending(mixed, META)
    raw_pending = dict(VALID, criterios=["[PENDENTE]"])
    assert "criterios" in required_pending(raw_pending, META)
    suggested = dict(
        VALID,
        comportamento_esperado=[f"{SUGGESTION_PREFIX} aceitar senha valida"],
        criterios=[f"{SUGGESTION_PREFIX} teste de login passa"],
    )
    assert required_pending(suggested, META) == []
    data2 = parse_model_json(json.dumps(dict(VALID, objetivo="corrigir [PENDENTE] depois")))
    assert PENDING not in data2["objetivo"]
    assert "objetivo" not in required_pending(data2, META)
    empty_obj = dict(VALID, objetivo=PENDING, contexto=PENDING)
    assert "objetivo" in required_pending(empty_obj, META)
    assert required_pending(parse_model_json(json.dumps(VALID)), META) == []
    data3 = parse_model_json(json.dumps(dict(VALID, observacoes=["ok", "falta [PENDENTE]"])))
    assert "observacoes" in required_pending(data3, META)
    cited = parse_model_json(json.dumps(dict(
        VALID,
        problemas=["O contexto do usuario citou ([PENDENTE]) literalmente"],
        observacoes=['Nenhuma. O texto tinha "[PENDENTE]" e `[PENDENTE]`.'],
    )))
    assert required_pending(cited, META) == []
    gap = parse_model_json(json.dumps(dict(
        VALID,
        observacoes=["Detalhes tecnicos de como o Forge aplica formatacao: [PENDENTE] se necessario"],
    )))
    assert "observacoes" in required_pending(gap, META)
    labeled = parse_model_json(json.dumps(dict(VALID, situacao_atual="Campo: [PENDENTE]")))
    assert "situacao_atual" in required_pending(labeled, META)


def test_short_context_infers_expected_and_acceptance_without_pending():
    payload = dict(
        VALID,
        objetivo="[PENDENTE]",
        contexto="[PENDENTE]",
        comportamento_esperado=["[PENDENTE]"],
        criterios=["[PENDENTE]"],
    )
    data = fill_inferred_sections(parse_model_json(json.dumps(payload)),
                                 "tarefa de teste, solicitado por carlos daniel")
    assert PENDING not in data["comportamento_esperado"][0]
    assert PENDING not in data["criterios"][0]
    assert data["comportamento_esperado"][0].startswith(SUGGESTION_PREFIX)
    assert data["criterios"][0].startswith(SUGGESTION_PREFIX)
    assert PENDING not in data["objetivo"]
    assert "tarefa de teste" in data["contexto"]
    assert required_pending(data, META) == []


def test_empty_context_keeps_objetivo_pending():
    payload = dict(
        VALID,
        objetivo="",
        contexto="",
        comportamento_esperado=["[PENDENTE]"],
        criterios=["[PENDENTE]"],
    )
    data = fill_inferred_sections(parse_model_json(json.dumps(payload)), "")
    assert data["objetivo"] == PENDING
    assert data["comportamento_esperado"][0].startswith(SUGGESTION_PREFIX)
    assert data["criterios"][0].startswith(SUGGESTION_PREFIX)
    assert PENDING not in data["comportamento_esperado"][0]
    assert PENDING not in data["criterios"][0]
    blocked = required_pending(data, META)
    assert "objetivo" in blocked
    assert "comportamento_esperado" not in blocked
    assert "criterios" not in blocked


def test_title_and_repo_validation():
    assert validate_repo("ferreiraeborzone/app") == "ferreiraeborzone/app"
    with pytest.raises(DraftError):
        validate_repo("../etc")
    bad = dict(VALID, title="titulo livre")
    assert parse_model_json(json.dumps(bad))["title"] == f"feat: {PENDING}"
    from forge_core.draft.template import TITLE_RE, validate_title
    assert TITLE_RE.match("feat: login recusa senha valida")
    assert TITLE_RE.match("fix(api)!: quebra")
    assert TITLE_RE.match("revert: desfaz a mudanca")
    assert validate_title("docs(readme): atualiza")
    with pytest.raises(DraftError) as ei:
        validate_title("WIP: sem conventional")
    assert ei.value.code == "invalid_title"


def test_match_option_accent_emoji_and_board_reread(tmp_path):
    field = {"id": "f-p", "name": "Prioridade", "options": [
        {"id": "o-high", "name": "🔴 Alta"},
        {"id": "o-low", "name": "Baixa"},
    ]}
    assert match_option(field, "Alta") == "o-high"
    assert match_option(field, "alta") == "o-high"
    assert names_match("🔴 Alta", "Alta")
    field2 = {"id": "f-t", "name": "Tipo", "options": [{"id": "o-bug", "name": "Manutenção"}]}
    assert match_option(field2, "Manutencao") == "o-bug"
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    gh = GhCli(runner=_gh_script({"blank_priority": True}), today=date(2026, 11, 8))
    svc = DraftService(TaskService(repo), FakeLLM(), gh, today=date(2026, 11, 8))
    result = svc.generate("falha", "acme/app", editor, tmp_path / "prio.md", META)
    with pytest.raises(DraftError) as ei:
        svc.publish(result, "acme/app", editor, META)
    assert ei.value.code == "board_mismatch"
    assert "prioridade" in ei.value.hint
    remote = parse_remote(TaskService(repo).get_task(result.task_id).context)
    assert remote.issue == 9 and remote.phase == "issue"
    assert sidecar_path(Path(result.path)).is_file()


def test_cursor_temp_cwd_deny_allowlist_payload_and_cleanup(tmp_path):
    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        seen["cwd"] = cwd
        seen["argv"] = argv
        seen["env"] = env
        seen["input"] = kwargs.get("input")
        seen["shell"] = kwargs.get("shell")
        seen["names"] = sorted(p.name for p in Path(cwd).iterdir())
        deny = json.loads((Path(cwd) / ".cursor" / "cli.json").read_text())["permissions"]["deny"]
        seen["deny"] = deny
        assert Path(cwd).resolve() != Path.home().resolve()
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(VALID).encode(), stderr=b"")

    host = {
        "PATH": "/bin", "HOME": str(tmp_path), "GH_TOKEN": "gho_secreto",
        "GITHUB_TOKEN": "ghs_secreto", "FORGE_DATABASE_URL": "sqlite:///x",
        "DATABASE_URL": "postgresql://x", "CURSOR_API_KEY": "cursor-session",
        "FORGE_GITHUB_CLIENT_ID": "abc",
    }
    adapter = CursorCliAdapter(runner=runner, env=host, model="test-model", agent_bin="agent")
    prompt = "CONTEXTO_DO_USUARIO:\nfalha no login\n"
    adapter.complete(prompt)
    assert seen["names"] == [".cursor"]
    assert seen["deny"] == list(DOCUMENTED_DENY)
    assert not any(f in seen["argv"] for f in FORBIDDEN_FLAGS)
    assert TRUST_FLAG in seen["argv"]
    assert "--mode" in seen["argv"] and "ask" in seen["argv"]
    assert prompt not in seen["argv"]
    assert seen["input"] == prompt.encode("utf-8")
    assert seen["shell"] is False
    assert "GH_TOKEN" not in seen["env"]
    assert adapter.last_stdin_eof is True
    tmp = seen["env"].get("TMP") or seen["env"].get("TEMP") or seen["env"].get("TMPDIR")
    assert tmp and Path(tmp).resolve() != Path(seen["cwd"]).resolve()
    assert seen["env"].get("NODE_OPTIONS") == "--max-old-space-size=512"
    assert "FORGE_" not in " ".join(seen["env"])
    assert not Path(adapter.last_workspace).exists()
    assert "Shell()" not in seen["deny"] and "Read()" not in seen["deny"]


def test_cursor_timeout_no_persist(tmp_path):
    def runner(*a, **k):
        raise subprocess.TimeoutExpired("agent", 1)

    adapter = CursorCliAdapter(runner=runner, env={"PATH": "/bin"}, agent_bin="agent")
    with pytest.raises(DraftError) as ei:
        adapter.complete("x")
    assert ei.value.code == "timeout"
    assert not Path(adapter.last_workspace).exists()


def test_trust_only_on_owned_forge_temp():
    adapter = CursorCliAdapter(agent_bin="agent")
    owned = "/tmp/forge-cursor-owned"
    adapter.last_workspace = owned
    with_trust = adapter._argv_for(owned, "agent")
    without = adapter._argv_for("/tmp/some-other-dir", "agent")
    assert TRUST_FLAG in with_trust
    assert TRUST_FLAG not in without
    assert TRUST_FLAG not in FORBIDDEN_FLAGS
    assert "--force" in FORBIDDEN_FLAGS and "--yolo" in FORBIDDEN_FLAGS
    assert "-f" in FORBIDDEN_FLAGS and "--approve-mcps" in FORBIDDEN_FLAGS


def test_resolve_agent_which_pathext_then_localappdata_then_missing():
    win_cmd = r"C:\Users\me\AppData\Local\cursor-agent\agent.cmd"
    env = {"PATH": r"C:\Users\me\AppData\Local\cursor-agent", "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC"}
    assert resolve_agent_executable(env, which=lambda name: win_cmd if name == "agent" else None, platform="win32") == win_cmd

    fallback = r"C:\Users\me\AppData\Local\cursor-agent\agent.cmd"
    env2 = {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}
    assert resolve_agent_executable(
        env2, which=lambda name: None, path_exists=lambda p: p == fallback, platform="win32",
    ) == fallback

    with pytest.raises(DraftError) as ei:
        resolve_agent_executable(
            {"LOCALAPPDATA": r"C:\empty"}, which=lambda name: None,
            path_exists=lambda p: False, platform="win32",
        )
    assert ei.value.code == "cursor_cli_missing"

    env3 = {"FORGE_CURSOR_AGENT": r"D:\custom\agent.exe", "LOCALAPPDATA": r"C:\Users\me\AppData\Local"}
    assert resolve_agent_executable(
        env3, which=lambda name: win_cmd, path_exists=lambda p: True, platform="win32",
    ) == r"D:\custom\agent.exe"


def test_prompt_goes_to_stdin_not_argv_multiline_long_cmd_chars():
    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        seen["argv"] = argv
        seen["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(argv, 0, stdout=b"ok", stderr=b"")

    special = "line1\nline2 & echo pwned | more ^ %PATH% \"quoted\" <file>\n"
    huge = special + ("x" * 9000)
    adapter = CursorCliAdapter(runner=runner, env={"PATH": "/bin"}, agent_bin="agent")
    adapter.complete(huge)
    assert seen["input"] == huge.encode("utf-8")
    assert huge not in seen["argv"]
    assert special not in seen["argv"]
    assert not any("&" in a or "|" in a or "^" in a for a in seen["argv"])
    joined = " ".join(seen["argv"])
    assert "pwned" not in joined
    assert TRUST_FLAG in seen["argv"]


def test_cursor_cli_error_redacts_and_truncates_stderr():
    token = "gho_" + ("a" * 20)
    pat = "github_pat_" + ("b" * 20)
    bearer = "Bearer super-secret-session"
    api_key = "cursor-live-key-xyz"
    long_tail = "Z" * 800
    stderr = f"fail {token} {pat} {bearer} CURSOR_API_KEY={api_key} {long_tail}"
    hint = format_cursor_cli_error(7, stderr.encode(), {"CURSOR_API_KEY": api_key})
    assert "exit=7" in hint
    assert token not in hint and pat not in hint
    assert "super-secret-session" not in hint
    assert api_key not in hint
    assert "***" in hint
    body = hint.split("stderr=", 1)[1]
    assert len(body) <= STDERR_SNIPPET

    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        seen["ok"] = True
        return subprocess.CompletedProcess(argv, 3, stdout=b"", stderr=stderr.encode())

    adapter = CursorCliAdapter(
        runner=runner, env={"PATH": "/bin", "CURSOR_API_KEY": api_key}, agent_bin="agent",
    )
    with pytest.raises(DraftError) as ei:
        adapter.complete("prompt")
    assert ei.value.code == "cursor_cli_error"
    assert "exit=3" in ei.value.hint
    assert token not in ei.value.hint
    assert api_key not in str(ei.value)


def test_env_filter_drops_forge_and_gh_tokens():
    src = {"PATH": "/bin", "GH_TOKEN": "x", "FORGE_CONFIG_DIR": "c", "HOME": "/h", "GITHUB_TOKEN": "y"}
    out = filter_env(src, GH_ENV_ALLOW)
    assert "GH_TOKEN" not in out and "FORGE_CONFIG_DIR" not in out
    assert "GITHUB_TOKEN" not in out


def test_windows_allowlist_keeps_systemroot_drops_secrets():
    src = {
        "SystemRoot": r"C:\Windows", "ComSpec": r"C:\Windows\system32\cmd.exe",
        "PATHEXT": ".COM;.EXE;.BAT;.CMD", "LOCALAPPDATA": r"C:\Users\me\AppData\Local",
        "USERPROFILE": r"C:\Users\me", "NUMBER_OF_PROCESSORS": "8",
        "PROCESSOR_ARCHITECTURE": "AMD64", "OS": "Windows_NT",
        "ProgramFiles": r"C:\Program Files", "ALLUSERSPROFILE": r"C:\ProgramData",
        "TEMP": r"C:\Windows\Temp", "CURSOR_API_KEY": "cursor-session",
        "GH_TOKEN": "gho_secret", "GITHUB_TOKEN": "ghs_secret",
        "FORGE_DATABASE_URL": "sqlite:///x", "DATABASE_URL": "postgresql://x",
        "NODE_OPTIONS": "--require evil.js --max-old-space-size=64",
        "gh_extra": "nope",
    }
    allow = cursor_env_allow("win32")
    assert "SYSTEMROOT" in {x.upper() for x in CURSOR_ENV_ALLOW_WIN}
    out = filter_env(src, allow)
    assert out["SystemRoot"] == r"C:\Windows"
    assert out["TEMP"] == r"C:\Windows\Temp"
    assert out["CURSOR_API_KEY"] == "cursor-session"
    assert "GH_TOKEN" not in out and "GITHUB_TOKEN" not in out
    assert "FORGE_DATABASE_URL" not in out and "DATABASE_URL" not in out
    assert "NODE_OPTIONS" not in out
    assert forge_node_options(src) == "--max-old-space-size=512"
    child_src = dict(src)
    child_src["FORGE_CURSOR_MAX_OLD_SPACE_MB"] = "768"
    from forge_core.draft.cursor_cli import build_cursor_child_env
    child = build_cursor_child_env(child_src, platform="win32", scratch_tmp=r"D:\scratch")
    assert child["NODE_OPTIONS"] == "--max-old-space-size=768"
    assert "--require" not in child["NODE_OPTIONS"]
    assert "FORGE_CURSOR_MAX_OLD_SPACE_MB" not in child
    assert child["TEMP"] == r"C:\Windows\Temp"
    assert child["TEMP"] != r"D:\scratch"


def test_posix_scratch_tmp_when_host_has_none_and_stdin_eof():
    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        seen["cwd"] = cwd
        seen["env"] = env
        seen["input"] = kwargs.get("input")
        seen["calls"] = seen.get("calls", 0) + 1
        return subprocess.CompletedProcess(argv, 0, stdout=b"ok", stderr=b"")

    adapter = CursorCliAdapter(runner=runner, env={"PATH": "/bin"}, agent_bin="agent", platform="linux")
    adapter.complete("hi")
    assert seen["calls"] == 1
    assert seen["input"] == b"hi"
    assert adapter.last_stdin_eof is True
    tmp = seen["env"]["TMPDIR"]
    assert Path(tmp).resolve() != Path(seen["cwd"]).resolve()
    assert Path(tmp).name.startswith("forge-cursor-scratch-") or not Path(tmp).exists()


def test_cursor_cli_error_uses_stdout_when_stderr_empty():
    gc = "Last few GCs ... Scavenge 52.6 (62.1) -> 49.5 (62.9) MB ... allocation failure"
    hint = format_cursor_cli_error(134, b"", {}, stdout=gc.encode())
    assert "exit=134" in hint
    assert "allocation failure" in hint
    assert len(hint.split("stderr=", 1)[1]) <= STDERR_SNIPPET


def test_doctor_prints_names_not_secrets():
    seen = []

    def runner(argv, cwd=None, env=None, **kwargs):
        seen.append(argv)
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=b"2026.11.10\n", stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"OK\n", stderr=b"")

    out = _Buf()
    env = {
        "PATH": "/bin", "HOME": "/h", "CURSOR_API_KEY": "super-secret-key",
        "GH_TOKEN": "gho_nope", "FORGE_CURSOR_AGENT": "agent",
        "FORGE_CURSOR_MODEL": "composer-2.5",
    }
    code = diagnose_cursor_cli(env, out=out, runner=runner, platform="linux")
    assert code == 0
    assert "super-secret-key" not in out.text
    assert "gho_nope" not in out.text
    assert "env_names:" in out.text
    assert "CURSOR_API_KEY" in out.text
    assert "agent_path:" in out.text
    assert "probe_exit: 0" in out.text
    assert "model=composer-2.5" in out.text
    probes = [a for a in seen if "-p" in a]
    assert probes and "--model" in probes[0] and "composer-2.5" in probes[0]
    assert any("--version" in a for a in seen)


def test_doctor_and_draft_use_the_same_model_resolution():
    env = {"FORGE_CURSOR_MODEL": "composer-2.5"}
    assert resolve_cursor_model(env) == "composer-2.5"
    assert resolve_cursor_model(env, flag="  other-model  ") == "other-model"
    assert resolve_cursor_model({}, flag="") is None
    assert resolve_cursor_model({}) is None
    draft_model = resolve_cursor_model(env, flag="")
    doctor_model = resolve_cursor_model(env, flag=None)
    assert draft_model == doctor_model == "composer-2.5"
    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        if "-p" in argv:
            seen["probe"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout=b"OK\n", stderr=b"")

    diagnose_cursor_cli(
        {"PATH": "/bin", "FORGE_CURSOR_AGENT": "agent", "FORGE_CURSOR_MODEL": "composer-2.5"},
        out=_Buf(), runner=runner, platform="linux",
    )
    adapter = CursorCliAdapter(
        runner=runner, env={"PATH": "/bin"}, agent_bin="agent",
        model=resolve_cursor_model({"FORGE_CURSOR_MODEL": "composer-2.5"}),
    )
    adapter.complete("x")
    assert seen["probe"].count("composer-2.5") == 1
    assert adapter.last_argv.count("composer-2.5") == 1
    assert adapter.last_argv[adapter.last_argv.index("--model") + 1] == seen["probe"][seen["probe"].index("--model") + 1]


def test_doctor_cli_flag_overrides_env_like_draft():
    env = {"PATH": "/bin", "FORGE_CURSOR_AGENT": "agent", "FORGE_CURSOR_MODEL": "from-env"}
    assert resolve_cursor_model(env, flag="from-flag") == "from-flag"
    seen = []

    def runner(argv, cwd=None, env=None, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=b"OK\n", stderr=b"")

    out = _Buf()
    code = diagnose_cursor_cli(env, out=out, runner=runner, platform="linux", model_flag="from-flag")
    assert code == 0
    assert "model=from-flag" in out.text
    probes = [a for a in seen if "-p" in a]
    assert "from-flag" in probes[0] and "from-env" not in probes[0]
    seen.clear()
    out2 = _Buf()
    diagnose_cursor_cli(
        {"PATH": "/bin", "FORGE_CURSOR_AGENT": "agent"},
        out=out2, runner=runner, platform="linux",
    )
    assert "model=(padrão da CLI)" in out2.text
    probes2 = [a for a in seen if "-p" in a]
    assert probes2 and "--model" not in probes2[0]


def test_cli_contexto_arquivo_stdin_editor_ok_viewer_denied(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    out, err = _Buf(), _Buf()
    login_gh.select("ana", 1001)
    llm = FakeLLM()
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    code = draft_run(
        ["draft", "--contexto", "falha no login do modulo x", "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "a.md"), "--tipo", "Bug", "--prioridade", "Alta", "--size", "3"],
        env, transport=login_gh, provider=llm, gh=gh, out=out, err=err, stdin=StringIO(""),
    )
    assert code == 0
    assert (tmp_path / "a.md").is_file()
    assert "CONTEXTO_DO_USUARIO" in llm.prompts[0]
    assert gh.calls == []
    tasks = TaskService(repo).list_tasks()
    assert len(tasks) == 1 and tasks[0].assignee_id == ASSIGNEE
    (tmp_path / "ctx.txt").write_text("segundo contexto em arquivo", encoding="utf-8")
    login_gh.select("ana", 1001)
    code = draft_run(
        ["draft", "--arquivo", str(tmp_path / "ctx.txt"), "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "from-file.md"), "--tipo", "Bug", "--prioridade", "Alta",
         "--size", "3"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=_Buf(), stdin=StringIO(""),
    )
    assert code == 0 and (tmp_path / "from-file.md").is_file()
    login_gh.select("ana", 1001)
    stdin = type("S", (), {"buffer": BytesIO("contexto stdin".encode()), "isatty": lambda self: False})()
    code = draft_run(
        ["draft", "--arquivo", "-", "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "from-stdin.md"), "--tipo", "Bug", "--prioridade", "Alta", "--size", "3"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=_Buf(), stdin=stdin,
    )
    assert code == 0 and (tmp_path / "from-stdin.md").is_file()

    assert auth_cli.run(["logout"], env, transport=login_gh, out=_Buf(), err=_Buf()) == 0
    login_gh.select("solta", 1004)
    err2 = _Buf()
    code = draft_run(
        ["draft", "--contexto", "x", "--repo", "ferreiraeborzone/app", "--output", str(tmp_path / "b.md")],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=err2, stdin=StringIO(""),
    )
    assert code == 1
    assert "forbidden" in err2.text


def test_context_flags_exclusive_utf8_and_limits(tmp_path):
    assert TextContext("  olá  ").load() == "olá"
    (tmp_path / "ok.txt").write_text("arquivo utf8", encoding="utf-8")
    assert FileContext(str(tmp_path / "ok.txt")).load() == "arquivo utf8"
    assert FileContext("-", stdin_read=lambda: "via stdin".encode("utf-8")).load() == "via stdin"
    with pytest.raises(DraftError) as ei:
        resolve_source(contexto="a", arquivo="b.txt", positional=None)
    assert ei.value.code == "context_ambiguous"
    with pytest.raises(DraftError) as ei:
        resolve_source(contexto="a", arquivo=None, positional="b")
    assert ei.value.code == "context_ambiguous"
    (tmp_path / "bin.txt").write_bytes(b"\xff\xfe not utf8")
    with pytest.raises(DraftError) as ei:
        FileContext(str(tmp_path / "bin.txt")).load()
    assert ei.value.code == "invalid_utf8"
    with pytest.raises(DraftError) as ei:
        FileContext("-", stdin_read=lambda: b"\x00abc").load()
    assert ei.value.code == "invalid_utf8"
    with pytest.raises(DraftError) as ei:
        TextContext("x" * (MAX_CONTEXT_BYTES + 1)).load()
    assert ei.value.code == "context_too_large"
    with pytest.raises(DraftError) as ei:
        FileContext(str(tmp_path / "missing.txt")).load()
    assert ei.value.code == "context_file"


def test_yes_does_not_skip_pending(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    err = _Buf()
    code = draft_run(
        ["draft", "--contexto", "contexto suficiente para redigir", "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "c.md"), "--yes"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1
    assert "pending_required" in err.text
    assert not any("issue" in a and "create" in a for a in gh.calls)


def test_yes_does_not_skip_partial_pending_in_list(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    payload = dict(VALID, criterios=["Teste passa", "falta [PENDENTE] aqui"])
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    out = _Buf()
    code = draft_run(
        ["draft", "--contexto", "ctx", "--repo", "acme/app", "--output", str(tmp_path / "p.md"),
         "--tipo", "Bug", "--prioridade", "Alta", "--size", "3", "--yes"],
        env, transport=login_gh, provider=FakeLLM(text=json.dumps(payload)), gh=gh,
        out=out, err=_Buf(), stdin=StringIO(""),
    )
    assert code == 0
    assert any(a[1:3] == ["issue", "create"] for a in gh.calls)
    body = (tmp_path / "p.md").read_text(encoding="utf-8")
    assert PENDING not in body.split("## Critérios de Aceite", 1)[1].split("## ", 1)[0]


def test_publish_happy_create_prints_url_not_json(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    svc = DraftService(TaskService(repo), FakeLLM(), gh, today=date(2026, 11, 8))
    result = svc.generate("falha", "acme/app", editor, tmp_path / "d.md", META)
    published = svc.publish(result, "acme/app", editor, META)
    assert published.remote.issue == 9
    creates = [c for c in gh.calls if c[1:3] == ["issue", "create"]]
    assert len(creates) == 1
    assert "--json" not in creates[0]
    assert any(c[1:3] == ["api", "graphql"] for c in gh.calls)
    assert not any(c[1:3] == ["project", "field-list"] for c in gh.calls)


def test_resume_after_partial_does_not_duplicate(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    boom = {"fail_add": True}
    gh = GhCli(runner=_gh_script(boom), today=date(2026, 11, 8))
    out_path = tmp_path / "g.md"
    code = draft_run(
        ["draft", "--contexto", "falha", "--repo", "acme/app", "--output", str(out_path),
         "--tipo", "Bug", "--prioridade", "Alta", "--size", "3", "--yes"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=_Buf(), stdin=StringIO(""),
    )
    assert code == 1
    tasks = TaskService(repo).list_tasks()
    assert len(tasks) == 1
    remote = parse_remote(tasks[0].context)
    assert remote.issue == 9
    assert sidecar_path(out_path).is_file()
    creates = [c for c in gh.calls if c[1:3] == ["issue", "create"]]
    assert len(creates) == 1
    boom["fail_add"] = False
    login_gh.select("ana", 1001)
    llm2 = FakeLLM()
    gh2 = GhCli(runner=_gh_script(boom), today=date(2026, 11, 8))
    out = _Buf()
    code = draft_run(
        ["draft", "--retomar", tasks[0].id, "--repo", "acme/app", "--output", str(out_path),
         "--tipo", "Bug", "--prioridade", "Alta", "--size", "3", "--yes"],
        env, transport=login_gh, provider=llm2, gh=gh2, out=out, err=_Buf(), stdin=StringIO(""),
    )
    assert code == 0
    assert llm2.prompts == []
    assert len([c for c in gh2.calls if c[1:3] == ["issue", "create"]]) == 0
    assert "Issue 9" in out.text


class _LoginSpy(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.device_starts = 0

    def post_form(self, url, data):
        if str(url).endswith("/device/code"):
            self.device_starts += 1
        return super().post_form(url, data)


class _TTY(StringIO):
    def isatty(self):
        return True


def test_resume_without_repo_restores_saved_params(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    out_path = tmp_path / "retomar.md"
    svc = DraftService(TaskService(repo), FakeLLM(), GhCli(runner=_gh_script(), today=date(2026, 11, 8)),
                       today=date(2026, 11, 8))
    generated = svc.generate("falha", "acme/app", editor, out_path, META)
    login_gh.select("ana", 1001)
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    out = _Buf()
    code = draft_run(
        ["draft", "--retomar", generated.task_id, "--yes"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=out, err=_Buf(), stdin=StringIO(""),
    )
    assert code == 0
    assert "Issue 9" in out.text
    assert any(c[1:3] == ["issue", "create"] for c in gh.calls)


def test_resume_repo_override_refused_when_issue_exists(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    boom = {"fail_add": True}
    out_path = tmp_path / "mix.md"
    code = draft_run(
        ["draft", "--contexto", "falha", "--repo", "acme/app", "--output", str(out_path),
         "--tipo", "Bug", "--prioridade", "Alta", "--size", "3", "--yes"],
        env, transport=login_gh, provider=FakeLLM(), gh=GhCli(runner=_gh_script(boom), today=date(2026, 11, 8)),
        out=_Buf(), err=_Buf(), stdin=StringIO(""),
    )
    assert code == 1
    tasks = TaskService(repo).list_tasks()
    login_gh.select("ana", 1001)
    err = _Buf()
    code = draft_run(
        ["draft", "--retomar", tasks[0].id, "--repo", "other/app", "--output", str(out_path), "--yes"],
        env, transport=login_gh, provider=FakeLLM(),
        gh=GhCli(runner=_gh_script(boom), today=date(2026, 11, 8)),
        out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1
    assert "repo_mismatch" in err.text


def test_file_exists_before_login_suggests_retomar(tmp_path):
    repo, _login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    out_path = tmp_path / "existe.md"
    generated = DraftService(TaskService(repo), FakeLLM()).generate("falha", "acme/app", editor, out_path, META)
    spy = _LoginSpy()
    llm = FakeLLM()
    err = _Buf()
    code = draft_run(
        ["draft", "--contexto", "de novo", "--repo", "acme/app", "--output", str(out_path),
         "--tipo", "Bug", "--prioridade", "Alta", "--size", "3"],
        env, transport=spy, provider=llm, gh=GhCli(runner=_gh_script(), today=date(2026, 11, 8)),
        out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1
    assert spy.device_starts == 0
    assert llm.prompts == []
    assert "file_exists" in err.text
    assert "--retomar" in err.text
    assert generated.task_id in err.text


def test_ask_confirm_s_sim_and_invalid_ss(tmp_path):
    def _ask(raw):
        out = _Buf()
        ok = ask_confirm("prev", yes=False, stdin=_TTY(raw), out=out)
        return ok, out.text

    assert _ask("s\n")[0] is True
    assert _ask(" SIM \n")[0] is True
    ok, text = _ask("ss\n")
    assert ok is False
    assert "Resposta inválida: responda s ou N. Cancelado." in text
    ok, text = _ask("\n")
    assert ok is False and "Cancelado." in text and "inválida" not in text
    ok, text = _ask("n\n")
    assert ok is False and "Resposta inválida" not in text
    ok, text = _ask("nao\n")
    assert ok is False and "Resposta inválida" not in text
    ok, text = _ask("não\n")
    assert ok is False and "Resposta inválida" not in text
    ok, text = _ask("yes\n")
    assert ok is False and "Resposta inválida: responda s ou N. Cancelado." in text


def test_checkpoint_survives_local_save_failure(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    svc = DraftService(TaskService(repo), FakeLLM(), gh, today=date(2026, 11, 8))
    result = svc.generate("falha", "acme/app", editor, tmp_path / "h.md", META)
    real = svc.tasks.update_task

    def boom(*a, **k):
        raise RuntimeError("db")

    svc.tasks.update_task = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        svc.publish(result, "acme/app", editor, META)
    assert sidecar_path(Path(result.path)).is_file()
    assert parse_remote(TaskService(repo).get_task(result.task_id).context).issue is None
    svc.tasks.update_task = real  # type: ignore[method-assign]
    resumed = svc.load_resume(result.task_id, Path(result.path), editor, "acme/app")
    assert resumed.remote.issue == 9
    published = svc.publish(resumed, "acme/app", editor, META)
    creates = [c for c in gh.calls if c[1:3] == ["issue", "create"]]
    assert len(creates) == 1
    assert published.remote.phase == "done"


def test_unexpected_remote_does_not_create_again(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    gh = GhCli(runner=_gh_script({"view_title": "outro titulo"}), today=date(2026, 11, 8))
    svc = DraftService(TaskService(repo), FakeLLM(), gh, today=date(2026, 11, 8))
    result = svc.generate("falha", "acme/app", editor, tmp_path / "i.md", META)
    sidecar_path(Path(result.path)).write_text(json.dumps({
        "issue": 9, "url": ISSUE_URL, "phase": "issue", "repo": "acme/app",
    }), encoding="utf-8")
    with pytest.raises(DraftError) as ei:
        svc.publish(result, "acme/app", editor, META)
    assert ei.value.code == "remote_mismatch"
    assert [c for c in gh.calls if c[1:3] == ["issue", "create"]] == []


def test_file_exists_not_overwritten(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    path = tmp_path / "e.md"
    path.write_text("keep", encoding="utf-8")
    svc = DraftService(TaskService(repo), FakeLLM())
    with pytest.raises(DraftError) as ei:
        svc.generate("falha", "acme/app", editor, path, META)
    assert ei.value.code == "file_exists"
    assert path.read_text(encoding="utf-8") == "keep"


def test_timeout_does_not_write_file_or_task(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    svc = DraftService(TaskService(repo), FakeLLM(err=DraftError("timeout")))
    path = tmp_path / "f.md"
    with pytest.raises(DraftError):
        svc.generate("falha", "acme/app", editor, path, META)
    assert not path.exists()
    assert TaskService(repo).list_tasks() == []


def test_model_required_without_config(tmp_path):
    _people(tmp_path)
    env = _env(tmp_path)
    env.pop("FORGE_CURSOR_MODEL")
    err = _Buf()
    gh_login = FakeGitHub()
    gh_login.select("ana", 1001)
    code = draft_run(
        ["draft", "--contexto", "x", "--repo", "acme/app", "--output", str(tmp_path / "m.md")],
        env, transport=gh_login, provider=None, gh=GhCli(runner=_gh_script()),
        out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1 and "model_required" in err.text


def _gh_script(opts=None):
    opts = opts or {}
    created = {"n": 0}

    def runner(argv, **kwargs):
        cmd = argv[1:]
        if cmd[:2] == ["issue", "create"] and "--json" in cmd:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown flag: --json")
        stdout = ""
        if cmd[:2] == ["auth", "status"]:
            stdout = "Logged in to github.com as danielxdrj\nToken scopes: 'repo', 'project', 'read:org'\n"
        elif cmd[:2] == ["project", "view"]:
            stdout = json.dumps({"id": "PVT_proj", "title": "IT Backlog", "number": 13})
        elif cmd[:2] == ["project", "field-list"]:
            stdout = json.dumps(FIELD_LIST_REAL)
        elif cmd[:2] == ["api", "graphql"]:
            blob = " ".join(cmd)
            if "ProjectV2Item" in blob:
                nodes = [
                    {"name": "Bug", "field": {"id": "f-t", "name": "Tipo"}},
                    {"name": "3", "field": {"id": "f-z", "name": "Size"}},
                    {"title": "Semana 45", "field": {"id": "f-s", "name": "Sprint"}},
                ]
                if not opts.get("blank_priority"):
                    nodes.append({"name": "🔴 Alta", "field": {"id": "f-p", "name": "Prioridade"}})
                stdout = json.dumps({"data": {"node": {"fieldValues": {"nodes": nodes}}}})
            else:
                stdout = json.dumps(GRAPHQL_FIELDS)
        elif cmd[:2] == ["issue", "create"]:
            created["n"] += 1
            stdout = ISSUE_URL + "\n"
        elif cmd[:2] == ["issue", "view"]:
            stdout = json.dumps({
                "number": 9, "url": ISSUE_URL,
                "title": opts.get("view_title", TITLE), "state": "OPEN",
            })
        elif cmd[:2] == ["project", "item-add"]:
            if opts.get("fail_add"):
                return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"fail add")
            stdout = json.dumps({"id": "PVTI_item"})
        elif cmd[:2] == ["project", "item-edit"]:
            stdout = "{}"
        elif cmd[:2] == ["issue", "develop"] and "--list" in cmd:
            stdout = ""
        elif cmd[:2] == ["issue", "develop"]:
            stdout = "https://github.com/acme/app/tree/9-login-recusa-senha-valida"
        else:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
        return subprocess.CompletedProcess(argv, 0, stdout=stdout.encode(), stderr=b"")
    return runner
