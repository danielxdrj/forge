"""Rascunho de issue: LLM falso, gh falso, isolamento Cursor, papéis, template. Sem rede."""
from __future__ import annotations

import json
import subprocess
from datetime import date
from io import StringIO
from pathlib import Path

import pytest

from auth_helpers import FakeGitHub, TEST_CLIENT_ID, bootstrap, person
from forge_core.agents.provider import ProviderResponse
from forge_core.draft.cli import run as draft_run
from forge_core.draft.cursor_cli import DOCUMENTED_DENY, FORBIDDEN_FLAGS, CursorCliAdapter
from forge_core.draft.envfilter import GH_ENV_ALLOW, filter_env
from forge_core.draft.github_gh import GhCli
from forge_core.draft.service import DraftService, parse_remote
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

FIELDS = {
    "id": "PVT_proj",
    "fields": [
        {"id": "f-s", "name": "Sprint", "iterations": [
            {"id": "it-now", "title": "Semana 45", "startDate": "2026-11-03", "duration": 7},
        ]},
        {"id": "f-t", "name": "Tipo", "options": [{"id": "o-bug", "name": "Bug"}]},
        {"id": "f-p", "name": "Prioridade", "options": [{"id": "o-high", "name": "Alta"}]},
        {"id": "f-z", "name": "Size", "options": [{"id": "o-3", "name": "3"}]},
    ],
}

META = {"tipo": "Bug", "prioridade": "Alta", "size": "3", "sprint": "", "escopo": ""}


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
        assert "forge" not in Path(cwd).name or Path(cwd).name.startswith("forge-cursor-")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(VALID).encode(), stderr=b"")

    host = {
        "PATH": "/bin", "HOME": str(tmp_path), "GH_TOKEN": "gho_secreto",
        "GITHUB_TOKEN": "ghs_secreto", "FORGE_DATABASE_URL": "sqlite:///x",
        "DATABASE_URL": "postgresql://x", "CURSOR_API_KEY": "cursor-session",
        "FORGE_GITHUB_CLIENT_ID": "abc",
    }
    adapter = CursorCliAdapter(runner=runner, env=host, model="composer-2.5")
    prompt = "CONTEXTO_DO_USUARIO:\nfalha no login\n"
    adapter.complete(prompt)
    assert seen["names"] == [".cursor"]
    assert seen["deny"] == list(DOCUMENTED_DENY)
    assert not any(f in seen["argv"] for f in FORBIDDEN_FLAGS)
    assert "--mode" in seen["argv"] and "ask" in seen["argv"]
    assert "--workspace" in seen["argv"]
    assert seen["argv"][-1] == prompt
    assert "GH_TOKEN" not in seen["env"] and "FORGE_DATABASE_URL" not in seen["env"]
    assert "GITHUB_TOKEN" not in seen["env"] and "DATABASE_URL" not in seen["env"]
    assert seen["env"].get("CURSOR_API_KEY") == "cursor-session"
    assert adapter.last_workspace is not None
    assert not Path(adapter.last_workspace).exists()
    assert "Shell()" not in seen["deny"] and "Read()" not in seen["deny"]


def test_cursor_timeout_no_persist(tmp_path):
    def runner(*a, **k):
        raise subprocess.TimeoutExpired("agent", 1)

    adapter = CursorCliAdapter(runner=runner, env={"PATH": "/bin"})
    with pytest.raises(DraftError) as ei:
        adapter.complete("x")
    assert ei.value.code == "timeout"
    assert adapter.last_workspace is not None
    assert not Path(adapter.last_workspace).exists()


def test_env_filter_drops_forge_and_gh_tokens():
    src = {"PATH": "/bin", "GH_TOKEN": "x", "FORGE_CONFIG_DIR": "c", "HOME": "/h"}
    out = filter_env(src, GH_ENV_ALLOW)
    assert "GH_TOKEN" not in out and "FORGE_CONFIG_DIR" not in out
    assert out["PATH"] == "/bin"


def test_cli_argument_and_file_editor_ok_viewer_denied(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = {
        "FORGE_CONFIG_DIR": str(tmp_path / "cfg"),
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'd.db'}",
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
    }
    out, err = _Buf(), _Buf()
    login_gh.select("ana", 1001)
    llm = FakeLLM()
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    code = draft_run(
        ["draft", "falha no login do modulo x", "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "a.md"), "--tipo", "Bug", "--prioridade", "Alta", "--size", "3"],
        env, transport=login_gh, provider=llm, gh=gh, out=out, err=err, stdin=StringIO(""),
    )
    assert code == 0
    assert (tmp_path / "a.md").is_file()
    assert "CONTEXTO_DO_USUARIO" in llm.prompts[0]
    assert "gho_" not in llm.prompts[0]
    assert "FORGE_DATABASE" not in llm.prompts[0]
    assert "Mutações se confirmado" in out.text
    assert gh.calls == []  # sem confirmação: gh não executado
    tasks = TaskService(repo).list_tasks()
    assert len(tasks) == 1 and tasks[0].assignee_id == ASSIGNEE
    (tmp_path / "ctx.txt").write_text("segundo contexto em arquivo", encoding="utf-8")
    login_gh.select("ana", 1001)
    code = draft_run(
        ["draft", "--file", str(tmp_path / "ctx.txt"), "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "from-file.md"), "--tipo", "Bug", "--prioridade", "Alta",
         "--size", "3"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=_Buf(), stdin=StringIO(""),
    )
    assert code == 0 and (tmp_path / "from-file.md").is_file()

    login_gh.select("solta", 1004)
    err2 = _Buf()
    code = draft_run(
        ["draft", "x", "--repo", "ferreiraeborzone/app", "--output", str(tmp_path / "b.md")],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=err2, stdin=StringIO(""),
    )
    assert code == 1
    assert "forbidden" in err2.text or "AuthorizationError" in err2.text or "forge-tasks" in err2.text


def test_yes_does_not_skip_pending(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = {
        "FORGE_CONFIG_DIR": str(tmp_path / "cfg"),
        "FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'd.db'}",
        "FORGE_GITHUB_CLIENT_ID": TEST_CLIENT_ID,
    }
    login_gh.select("ana", 1001)
    gh = GhCli(runner=_gh_script(), today=date(2026, 11, 8))
    err = _Buf()
    code = draft_run(
        ["draft", "contexto suficiente para redigir", "--repo", "ferreiraeborzone/app",
         "--output", str(tmp_path / "c.md"), "--yes"],
        env, transport=login_gh, provider=FakeLLM(), gh=gh, out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1
    assert "pending_required" in err.text
    assert not any(a[1] == "issue" and a[2] == "create" for a in gh.calls)


def test_publish_happy_and_retry_does_not_duplicate(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    svc = DraftService(TaskService(repo), FakeLLM(), GhCli(runner=_gh_script(), today=date(2026, 11, 8)),
                       today=date(2026, 11, 8))
    svc.gh.project_id = None
    result = svc.generate("falha", "acme/app", editor, tmp_path / "d.md", META)
    published = svc.publish(result, "acme/app", editor, META)
    assert published.remote.issue == 9
    assert published.remote.branch == "9-login-recusa-senha-valida"
    creates = [c for c in svc.gh.calls if c[1:3] == ["issue", "create"]]
    assert len(creates) == 1
    again = svc.publish(published, "acme/app", editor, META)
    creates2 = [c for c in svc.gh.calls if c[1:3] == ["issue", "create"]]
    assert len(creates2) == 1
    assert again.remote.issue == 9
    task = TaskService(repo).get_task(result.task_id)
    remote = parse_remote(task.context)
    assert remote.phase == "done" and remote.url.endswith("/issues/9")


def test_file_exists_not_overwritten(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    path = tmp_path / "e.md"
    path.write_text("keep", encoding="utf-8")
    svc = DraftService(TaskService(repo), FakeLLM())
    with pytest.raises(DraftError) as ei:
        svc.generate("falha", "acme/app", editor, path, META)
    assert ei.value.code == "file_exists"
    assert path.read_text(encoding="utf-8") == "keep"
    assert TaskService(repo).list_tasks() == []


def test_timeout_does_not_write_file_or_task(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    svc = DraftService(TaskService(repo), FakeLLM(err=DraftError("timeout")))
    path = tmp_path / "f.md"
    with pytest.raises(DraftError):
        svc.generate("falha", "acme/app", editor, path, META)
    assert not path.exists()
    assert TaskService(repo).list_tasks() == []


def test_partial_board_failure_keeps_issue_number(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    def runner(argv, **kwargs):
        if argv[1:3] == ["project", "item-add"]:
            raise DraftError("gh_error")
        return _gh_script()(argv, **kwargs)

    svc = DraftService(TaskService(repo), FakeLLM(), GhCli(runner=runner, today=date(2026, 11, 8)),
                       today=date(2026, 11, 8))
    result = svc.generate("falha", "acme/app", editor, tmp_path / "g.md", META)
    with pytest.raises(DraftError):
        svc.publish(result, "acme/app", editor, META)
    task = TaskService(repo).get_task(result.task_id)
    remote = parse_remote(task.context)
    assert remote.issue == 9 and remote.phase == "issue"


def _gh_script():
    def runner(argv, **kwargs):
        cmd = argv[1:]
        stdout = ""
        if cmd[:2] == ["auth", "status"]:
            stdout = "Logged in to github.com as danielxdrj\nToken scopes: 'repo', 'project', 'read:org'\n"
        elif cmd[:2] == ["project", "view"]:
            stdout = json.dumps({"id": "PVT_proj", "title": "IT Backlog", "number": 13})
        elif cmd[:2] == ["project", "field-list"]:
            stdout = json.dumps(FIELDS)
        elif cmd[:2] == ["issue", "create"]:
            stdout = json.dumps({"number": 9, "url": "https://github.com/acme/app/issues/9"})
        elif cmd[:2] == ["project", "item-add"]:
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
