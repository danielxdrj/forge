"""Resolver: motor e gh falsos. Sem GitHub real e sem LLM real."""
from __future__ import annotations

import json
import os
import subprocess
from io import StringIO
from pathlib import Path

import pytest

from auth_helpers import FakeGitHub, TEST_CLIENT_ID, bootstrap, person
from forge_core.agents.provider import ProviderResponse
from forge_core.errors import AgentError, AuthorizationError, DraftError
from forge_core.draft.cursor_cli import (
    FORBIDDEN_FLAGS,
    IMPLEMENTER_DENY,
    IMPLEMENTER_MODE,
    TRUST_FLAG,
    implementer_adapter,
)
from forge_core.draft.envfilter import assert_no_host_secrets
from forge_core.draft.github_gh import GhCli
from forge_core.draft.service import ask_confirm
from forge_core.resolver.cli import run as resolver_run
from forge_core.resolver.gitops import GitCli
from forge_core.resolver.service import ResolverService, parse_issue_ref
from forge_core.resolver.validate import validate_diff
from forge_core.storage import open_repository
from forge_core.tasks import TaskService

ISSUE_REF = "acme/app#9"
PR_URL = "https://github.com/acme/app/pull/3"


class _Buf:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass


class _TTY(StringIO):
    def isatty(self):
        return True


class _LoginSpy(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.device_starts = 0

    def post_form(self, url, data):
        if str(url).endswith("/device/code"):
            self.device_starts += 1
        return super().post_form(url, data)


class FakeImplementer:
    name = "fake-impl"

    def __init__(self, write_rel="src/fix.py", extra=None, report="alterou src/fix.py\ntestes não rodados"):
        self.write_rel = write_rel
        self.extra = extra
        self.report = report
        self.prompts = []
        self.workspace = None
        self.push_calls = 0

    def complete(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        root = Path(self.workspace)
        path = root / self.write_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixed\n", encoding="utf-8")
        if self.extra:
            self.extra(root)
        return ProviderResponse(text=self.report)


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
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": str(tmp_path),
    }


def _git_init(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True, env=env)
    (dest / "README.md").write_text("# app\n", encoding="utf-8")
    (dest / "src").mkdir(exist_ok=True)
    (dest / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (dest / "docs").mkdir(exist_ok=True)
    (dest / "docs" / "note.md").write_text("doc\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=dest, check=True, capture_output=True, env=env,
    )
    bare = dest.parent / f"{dest.name}.git"
    if not bare.exists():
        subprocess.run(["git", "clone", "--bare", str(dest), str(bare)], check=True, capture_output=True, env=env)
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=dest, check=True, capture_output=True, env=env)


def _gh_script(opts=None):
    opts = opts or {}

    def runner(argv, cwd=None, env=None, **kwargs):
        cmd = argv[1:]
        stdout = ""
        if cmd[:2] == ["auth", "status"]:
            stdout = "Logged in to github.com\n"
        elif cmd[:2] == ["repo", "clone"]:
            dest = Path(cmd[3])
            _git_init(dest)
            stdout = f"cloned into {dest}\n"
        elif cmd[:2] == ["issue", "view"]:
            stdout = json.dumps({
                "number": 9, "url": "https://github.com/acme/app/issues/9",
                "title": "fix: login recusa senha", "state": "OPEN",
                "body": "Ajuste src/app.py e docs/note.md",
                "comments": [{"body": "ok", "author": {"login": "ana"}}],
            })
        elif cmd[:2] == ["issue", "develop"] and "--list" in cmd:
            stdout = opts.get("branches", "")
        elif cmd[:2] == ["pr", "create"]:
            assert "--draft" in cmd
            assert "--merge" not in cmd
            body_i = cmd.index("--body") + 1
            assert "Closes #9" in cmd[body_i]
            stdout = PR_URL + "\n"
        else:
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")
        return subprocess.CompletedProcess(argv, 0, stdout=stdout.encode(), stderr=b"")
    return runner


def test_parse_issue_ref():
    assert parse_issue_ref("acme/app#9") == ("acme/app", 9)
    with pytest.raises(DraftError) as ei:
        parse_issue_ref("acme/app")
    assert ei.value.code == "invalid_issue_ref"


def test_editor_required_owner_is_not_enough(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    gh = GhCli(runner=_gh_script())
    impl = FakeImplementer()
    svc = ResolverService(TaskService(repo), impl, gh, git=GitCli(env=_env(tmp_path)))
    with pytest.raises(AuthorizationError):
        svc.start(ISSUE_REF, owner)
    with pytest.raises(AuthorizationError):
        svc.start(ISSUE_REF, viewer)
    result = svc.start(ISSUE_REF, editor, keep_clone=True)
    assert result.state.phase == "validated"
    assert impl.prompts and "PACOTE" in impl.prompts[0]
    assert "gh push" not in " ".join(" ".join(c) for c in gh.calls)
    svc.cleanup(result.state)


def test_implementer_env_and_argv_no_push(tmp_path):
    clone = tmp_path / "forge-resolver-ws"
    _git_init(clone)
    seen = {}

    def runner(argv, cwd=None, env=None, **kwargs):
        seen["cwd"] = cwd
        seen["argv"] = argv
        seen["env"] = env
        seen["input"] = kwargs.get("input")
        deny = json.loads((Path(cwd) / ".cursor" / "cli.json").read_text())["permissions"]["deny"]
        seen["deny"] = deny
        return subprocess.CompletedProcess(argv, 0, stdout="ok\ntestes nao rodados".encode(), stderr=b"")

    host = {
        "PATH": "/bin", "HOME": str(tmp_path), "GH_TOKEN": "gho_secreto",
        "GITHUB_TOKEN": "ghs_secreto", "FORGE_DATABASE_URL": "sqlite:///x",
        "DATABASE_URL": "postgresql://x", "CURSOR_API_KEY": "cursor-session",
        "FORGE_CURSOR_MODEL": "m", "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
    }
    adapter = implementer_adapter(
        runner=runner, env=host, model="test-model", agent_bin="agent",
        workspace=str(clone),
    )
    adapter.complete("prompt-implementador")
    assert Path(seen["cwd"]).resolve() == clone.resolve()
    assert TRUST_FLAG in seen["argv"]
    assert not any(f in seen["argv"] for f in FORBIDDEN_FLAGS)
    assert IMPLEMENTER_MODE in seen["argv"]
    assert "ask" not in seen["argv"]
    assert seen["input"] == b"prompt-implementador"
    assert "GH_TOKEN" not in seen["env"] and "FORGE_DATABASE_URL" not in seen["env"]
    assert_no_host_secrets(seen["env"])
    assert list(IMPLEMENTER_DENY) == seen["deny"] or set(IMPLEMENTER_DENY) <= set(seen["deny"])
    assert "push" not in seen["argv"] and "gh" not in seen["argv"]
    scratch = adapter.last_scratch
    assert scratch
    assert str(Path(seen["env"]["GIT_CONFIG_GLOBAL"])).startswith(scratch)
    assert str(Path(seen["env"]["GH_CONFIG_DIR"])).startswith(scratch)
    assert "SSH_AUTH_SOCK" not in seen["env"]
    assert seen["env"].get("GIT_CONFIG_NOSYSTEM") == "1"
    assert seen["env"].get("GCM_INTERACTIVE") == "never"


def test_validate_sensitive_limit_and_outside(tmp_path):
    clone = tmp_path / "c"
    clone.mkdir()
    with pytest.raises(DraftError) as ei:
        validate_diff("diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n+SECRET=1\n", clone)
    assert ei.value.code == "sensitive_diff"
    huge = "diff --git a/a.py b/a.py\n" + "\n".join(["+x"] * 5000)
    with pytest.raises(DraftError) as ei:
        validate_diff(huge, clone)
    assert ei.value.code == "diff_too_large"
    with pytest.raises(DraftError) as ei:
        validate_diff("diff --git a/../../etc/passwd b/../../etc/passwd\n+x\n", clone)
    assert ei.value.code == "diff_outside_clone"
    with pytest.raises(DraftError) as ei:
        validate_diff("diff --git a/.gitattributes b/.gitattributes\n+* filter=evil\n", clone)
    assert ei.value.code == "sensitive_diff"
    with pytest.raises(DraftError) as ei:
        validate_diff("diff --git a/.gitmodules b/.gitmodules\n+[submodule]\n", clone)
    assert ei.value.code == "sensitive_diff"


def test_confirm_n_does_not_push(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    gh = GhCli(runner=_gh_script())
    git = GitCli(env=env)
    impl = FakeImplementer()
    out, err = _Buf(), _Buf()
    code = resolver_run(
        ["resolver", ISSUE_REF], env, transport=login_gh, provider=impl, gh=gh, git=git,
        out=out, err=err, stdin=_TTY("n\n"),
    )
    assert code == 0
    assert not any(c[1:3] == ["pr", "create"] for c in gh.calls)
    assert not any("push" in c for c in git.calls)


def test_confirm_s_push_draft_pr_closes(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    gh = GhCli(runner=_gh_script())
    git = GitCli(env=env)
    impl = FakeImplementer()
    out = _Buf()
    code = resolver_run(
        ["resolver", ISSUE_REF], env, transport=login_gh, provider=impl, gh=gh, git=git,
        out=out, err=_Buf(), stdin=_TTY("s\n"),
    )
    assert code == 0
    assert PR_URL in out.text
    assert any(c[1:3] == ["pr", "create"] and "--draft" in c for c in gh.calls)
    assert any("Closes #9" in " ".join(c) for c in gh.calls)
    assert any("push" in c and "HEAD:refs/heads/" in " ".join(c) for c in git.calls)
    assert any("--no-verify" in c for c in git.calls if "commit" in c)
    assert any("--no-verify" in c for c in git.calls if "push" in c)
    assert not any("merge" in c for c in gh.calls)
    audits = [a for a in repo.list_audit() if a.action == "resolver.approve"]
    assert audits and "hash=" in audits[-1].result
    assert editor.identity_id == audits[-1].actor


def test_invalid_confirm_message():
    out = _Buf()
    ok = ask_confirm("p", yes=False, stdin=_TTY("ss\n"), out=out,
                     question="Publicar branch e abrir PR em rascunho no GitHub? [s/N]")
    assert ok is False
    assert "responda s ou N" in out.text


def test_cheap_validation_before_login(tmp_path):
    _people(tmp_path)
    env = _env(tmp_path)
    spy = _LoginSpy()
    err = _Buf()
    code = resolver_run(
        ["resolver", "not-a-ref"], env, transport=spy, provider=FakeImplementer(),
        gh=GhCli(runner=_gh_script()), git=GitCli(env=env), out=_Buf(), err=err, stdin=StringIO(""),
    )
    assert code == 1
    assert spy.device_starts == 0
    assert "invalid_issue_ref" in err.text
    env2 = dict(env)
    env2.pop("FORGE_CURSOR_MODEL")
    spy2 = _LoginSpy()
    err2 = _Buf()
    code = resolver_run(
        ["resolver", ISSUE_REF], env2, transport=spy2, provider=None,
        gh=GhCli(runner=_gh_script()), git=GitCli(env=env2), out=_Buf(), err=err2, stdin=StringIO(""),
    )
    assert code == 1 and spy2.device_starts == 0 and "model_required" in err2.text


def test_resume_restores_params(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    gh = GhCli(runner=_gh_script())
    git = GitCli(env=env)
    impl = FakeImplementer()
    svc = ResolverService(TaskService(repo), impl, gh, git=git)
    first = svc.start(ISSUE_REF, editor, model="m1", keep_clone=True)
    tid = first.task_id
    clone = first.state.clone
    assert Path(clone).is_dir()
    impl2 = FakeImplementer()
    svc2 = ResolverService(TaskService(repo), impl2, gh, git=git)
    resumed = svc2.load_resume(tid, editor)
    assert resumed.state.phase == "validated"
    assert resumed.state.repo == "acme/app"
    assert impl2.prompts == []
    resumed.state.keep_clone = False
    svc2.cleanup(resumed.state)


def test_motor_sees_no_origin_and_cli_json_excluded(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    seen = {}

    def extra(root: Path):
        seen["remotes"] = subprocess.check_output(["git", "remote"], cwd=root, text=True).strip()
        (root / ".cursor").mkdir(exist_ok=True)
        (root / ".cursor" / "cli.json").write_text("{}", encoding="utf-8")

    impl = FakeImplementer(extra=extra)
    svc = ResolverService(TaskService(repo), impl, GhCli(runner=_gh_script()), git=GitCli(env=_env(tmp_path)))
    result = svc.start(ISSUE_REF, editor, keep_clone=True)
    assert seen.get("remotes") == ""
    assert ".cursor" not in result.diff
    log = subprocess.check_output(["git", "log", "-1", "--oneline"], cwd=result.state.clone, text=True)
    assert "fix: resolve" not in log
    svc.cleanup(result.state)


def test_git_meta_tampered_hooks_and_config(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    marker_holder = {}

    def install_hooks(root: Path):
        hooks = root / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        marker = root / "HOOK_RAN"
        marker_holder["path"] = marker
        for name in ("pre-commit", "post-commit", "pre-push"):
            path = hooks / name
            path.write_text(f"#!/bin/sh\necho ran > '{marker}'\n", encoding="utf-8")
            path.chmod(0o755)

    svc = ResolverService(
        TaskService(repo), FakeImplementer(extra=install_hooks),
        GhCli(runner=_gh_script()), git=GitCli(env=_env(tmp_path)),
    )
    with pytest.raises(DraftError) as ei:
        svc.start(ISSUE_REF, editor, keep_clone=True)
    assert ei.value.code == "git_meta_tampered"
    assert not marker_holder["path"].exists()

    def tweak_config(root: Path):
        cfg = root / ".git" / "config"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[evil]\nfoo = 1\n", encoding="utf-8")

    svc2 = ResolverService(
        TaskService(repo), FakeImplementer(extra=tweak_config),
        GhCli(runner=_gh_script()), git=GitCli(env=_env(tmp_path)),
    )
    with pytest.raises(DraftError) as ei:
        svc2.start(ISSUE_REF, editor, keep_clone=True)
    assert ei.value.code == "git_meta_tampered"


def test_gitattributes_in_diff_refused(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    svc = ResolverService(
        TaskService(repo), FakeImplementer(write_rel=".gitattributes"),
        GhCli(runner=_gh_script()), git=GitCli(env=_env(tmp_path)),
    )
    with pytest.raises(DraftError) as ei:
        svc.start(ISSUE_REF, editor, keep_clone=True)
    assert ei.value.code == "sensitive_diff"


def test_diff_changed_between_preview_and_confirm(tmp_path):
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    git = GitCli(env=_env(tmp_path))
    svc = ResolverService(TaskService(repo), FakeImplementer(), GhCli(runner=_gh_script()), git=git)
    result = svc.start(ISSUE_REF, editor, keep_clone=True)
    (Path(result.state.clone) / "src" / "fix.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(DraftError) as ei:
        svc.confirm_and_publish(result, editor)
    assert ei.value.code == "diff_changed"
    assert not any("push" in c for c in git.calls)
    impl2 = FakeImplementer()
    svc2 = ResolverService(TaskService(repo), impl2, GhCli(runner=_gh_script()), git=git)
    with pytest.raises(DraftError) as ei:
        svc2.load_resume(result.task_id, editor)
    assert ei.value.code == "diff_changed"
    assert impl2.prompts == []
    result.state.keep_clone = False
    svc.cleanup(result.state)


def test_privileged_agents_still_blocked():
    from forge_core.agents.registry import AgentRegistry
    from forge_core.agents.spec import AgentSpec

    class Writer:
        spec = AgentSpec(
            name="writer", responsibility="r", scope="s", tools=(),
            permissions=("write",), execution="e",
        )

        def run(self, ctx):
            return None

    with pytest.raises(AgentError, match="privileged agents disabled"):
        AgentRegistry().register(Writer())


def test_draft_cli_resolver_subcommand(tmp_path):
    from forge_core.draft.cli import run as draft_run
    repo, login_gh, owner, editor, viewer = _people(tmp_path)
    env = _env(tmp_path)
    login_gh.select("ana", 1001)
    gh = GhCli(runner=_gh_script())
    git = GitCli(env=env)
    out = _Buf()
    code = draft_run(
        ["resolver", ISSUE_REF], env, transport=login_gh, provider=FakeImplementer(),
        gh=gh, git=git, out=out, err=_Buf(), stdin=_TTY("s\n"),
    )
    assert code == 0
    assert PR_URL in out.text
