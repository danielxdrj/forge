"""Rascunho de issue: LLM falso, gh falso fiel ao CLI real. Sem rede."""
from __future__ import annotations

import json
import subprocess
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from auth_helpers import FakeGitHub, TEST_CLIENT_ID, bootstrap, person
from forge_core.agents.provider import ProviderResponse
from forge_core.draft.cli import run as draft_run
from forge_core.draft.context import MAX_CONTEXT_BYTES, FileContext, TextContext, resolve_source
from forge_core.draft.cursor_cli import DOCUMENTED_DENY, FORBIDDEN_FLAGS, CursorCliAdapter
from forge_core.draft.envfilter import GH_ENV_ALLOW, filter_env
from forge_core.draft.github_gh import GhCli
from forge_core.draft.service import DraftService, parse_remote, sidecar_path
from forge_core.draft.template import (
    ASSIGNEE, PENDING, parse_model_json, render, required_pending, validate_repo,
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
                                 "startDate": "2026-11-03", "duration": 7},
                            ],
                            "completedIterations": [],
                        },
                    },
                    {"id": "f-t", "name": "Tipo", "options": [{"id": "o-bug", "name": "Bug"}]},
                    {"id": "f-p", "name": "Prioridade", "options": [{"id": "o-high", "name": "Alta"}]},
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
    }


def test_template_order_and_pending_and_no_scope():
    data = parse_model_json(json.dumps(VALID))
    body = render(data)
    order = ["Solicitado Por", "Objetivo", "Contexto", "Foram reportados os seguintes problemas:",
             "Situação Atual", "Comportamento Esperado", "Critérios de Aceite", "Observações"]
    positions = [body.index(h) for h in order]
    assert positions == sorted(positions)
    assert "Escopo" not in body
    incomplete = dict(VALID, solicitado_por="Descreva o objetivo da solicitação aqui")
    parsed = parse_model_json(json.dumps(incomplete))
    assert parsed["solicitado_por"] == PENDING
    with pytest.raises(DraftError) as ei:
        parse_model_json(json.dumps(dict(VALID, objetivo="ok\n## Escopo\nnao")))
    assert ei.value.code == "scope_in_body"


def test_any_pending_marker_blocks_remote():
    data = parse_model_json(json.dumps(dict(VALID, criterios=["Teste passa", "[PENDENTE]"])))
    blocked = required_pending(data, META)
    assert "criterios" in blocked
    data2 = parse_model_json(json.dumps(dict(VALID, objetivo="corrigir [PENDENTE] depois")))
    assert "objetivo" in required_pending(data2, META)
    assert required_pending(parse_model_json(json.dumps(VALID)), META) == []


def test_title_and_repo_validation():
    assert validate_repo("ferreiraeborzone/app") == "ferreiraeborzone/app"
    with pytest.raises(DraftError):
        validate_repo("../etc")
    bad = dict(VALID, title="titulo livre")
    assert parse_model_json(json.dumps(bad))["title"] == f"feat: {PENDING}"


def test_cursor_temp_cwd_deny_allowlist_payload_and_cleanup(tmp_path):
    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        seen["cwd"] = cwd
        seen["argv"] = argv
        seen["env"] = env
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
    adapter = CursorCliAdapter(runner=runner, env=host, model="test-model")
    prompt = "CONTEXTO_DO_USUARIO:\nfalha no login\n"
    adapter.complete(prompt)
    assert seen["names"] == [".cursor"]
    assert seen["deny"] == list(DOCUMENTED_DENY)
    assert not any(f in seen["argv"] for f in FORBIDDEN_FLAGS)
    assert "--mode" in seen["argv"] and "ask" in seen["argv"]
    assert "GH_TOKEN" not in seen["env"]
    assert not Path(adapter.last_workspace).exists()
    assert "Shell()" not in seen["deny"] and "Read()" not in seen["deny"]


def test_cursor_timeout_no_persist(tmp_path):
    def runner(*a, **k):
        raise subprocess.TimeoutExpired("agent", 1)

    adapter = CursorCliAdapter(runner=runner, env={"PATH": "/bin"})
    with pytest.raises(DraftError) as ei:
        adapter.complete("x")
    assert ei.value.code == "timeout"
    assert not Path(adapter.last_workspace).exists()


def test_env_filter_drops_forge_and_gh_tokens():
    src = {"PATH": "/bin", "GH_TOKEN": "x", "FORGE_CONFIG_DIR": "c", "HOME": "/h"}
    out = filter_env(src, GH_ENV_ALLOW)
    assert "GH_TOKEN" not in out and "FORGE_CONFIG_DIR" not in out


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
    err = _Buf()
    code = draft_run(
        ["draft", "--contexto", "ctx", "--repo", "acme/app", "--output", str(tmp_path / "p.md"),
         "--tipo", "Bug", "--prioridade", "Alta", "--size", "3", "--yes"],
        env, transport=login_gh, provider=FakeLLM(text=json.dumps(payload)), gh=gh,
        out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1 and "pending_required" in err.text
    assert not any(a[1:3] == ["issue", "create"] for a in gh.calls)


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
