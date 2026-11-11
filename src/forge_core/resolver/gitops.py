"""Git local no clone temporário. O Forge faz commit/push; o motor não recebe GH_TOKEN."""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from ..draft.envfilter import filter_env
from ..errors import DraftError

Runner = Callable[..., subprocess.CompletedProcess]
GIT_ENV_ALLOW = frozenset({
    "PATH", "PATHEXT", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "USERNAME", "USER", "OS", "LANG", "LC_ALL", "LC_CTYPE",
})
DEFAULT_TIMEOUT = 60
MAX_OUTPUT = 256 * 1024
CURSOR_EXCLUDE = ".cursor/\n.cursor/**\n"


class GitCli:
    def __init__(self, *, env: Mapping[str, str] | None = None, runner: Runner | None = None,
                 timeout: int = DEFAULT_TIMEOUT):
        self._env = env
        self._runner = runner
        self.timeout = timeout
        self.calls: list[list[str]] = []
        self._hooks = tempfile.mkdtemp(prefix="forge-git-hooks-")
        cfg = tempfile.NamedTemporaryFile(prefix="forge-gitconfig-", suffix=".empty", delete=False)
        cfg.write(b"")
        cfg.close()
        self._global_cfg = cfg.name

    def _env_os(self, *, for_push: bool = False) -> dict[str, str]:
        child = filter_env(self._env or os.environ, GIT_ENV_ALLOW)
        child["GIT_TERMINAL_PROMPT"] = "0"
        if not for_push:
            child["GIT_CONFIG_NOSYSTEM"] = "1"
            child["GIT_CONFIG_GLOBAL"] = self._global_cfg
        return child

    def _prefix(self) -> list[str]:
        return ["-c", f"core.hooksPath={self._hooks}", "-c", "core.fsmonitor=false"]

    def run(self, args: list[str], *, cwd: str, for_push: bool = False) -> str:
        argv = ["git", *self._prefix(), *args]
        self.calls.append(argv)
        run = self._runner or subprocess.run
        try:
            proc = run(
                argv, cwd=cwd, env=self._env_os(for_push=for_push), capture_output=True,
                check=False, shell=False, timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise DraftError("git_missing") from exc
        except subprocess.TimeoutExpired as exc:
            raise DraftError("timeout") from exc
        raw = proc.stdout or b""
        if len(raw) > MAX_OUTPUT:
            raise DraftError("output_too_large")
        if proc.returncode != 0:
            raise DraftError("git_error")
        return raw.decode("utf-8", "replace")

    def checkout_or_create(self, cwd: str, branch: str, existing: bool) -> None:
        if existing:
            try:
                self.run(["checkout", branch], cwd=cwd)
                return
            except DraftError:
                self.run(["checkout", "-B", branch], cwd=cwd)
                return
        self.run(["checkout", "-B", branch], cwd=cwd)

    def fetch_branch(self, cwd: str, branch: str) -> None:
        try:
            self.run(["fetch", "origin", branch], cwd=cwd)
        except DraftError:
            return

    def status(self, cwd: str) -> str:
        return self.run(["status", "--porcelain"], cwd=cwd)

    def working_tree_diff(self, cwd: str) -> str:
        """Diff do working tree incluindo arquivos novos, sem commit. Respeita exclude."""
        self.run(["add", "-A"], cwd=cwd)
        diff = self.run(["diff", "--cached"], cwd=cwd)
        self.run(["reset", "HEAD"], cwd=cwd)
        return diff

    def add_all(self, cwd: str) -> None:
        self.run(["add", "-A"], cwd=cwd)

    def commit(self, cwd: str, message: str) -> None:
        self.run([
            "-c", "user.email=forge@example.invalid",
            "-c", "user.name=Forge",
            "commit", "--no-verify", "-m", message,
        ], cwd=cwd)

    def push(self, cwd: str, branch: str) -> None:
        self.run(
            ["push", "--no-verify", "origin", f"HEAD:refs/heads/{branch}"],
            cwd=cwd, for_push=True,
        )

    def ls_files(self, cwd: str) -> list[str]:
        text = self.run(["ls-files"], cwd=cwd)
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def remote_url(self, cwd: str, name: str = "origin") -> str:
        return self.run(["remote", "get-url", name], cwd=cwd).strip()

    def remote_remove(self, cwd: str, name: str = "origin") -> None:
        self.run(["remote", "remove", name], cwd=cwd)

    def remote_add(self, cwd: str, url: str, name: str = "origin") -> None:
        try:
            self.run(["remote", "remove", name], cwd=cwd)
        except DraftError:
            pass
        self.run(["remote", "add", name, url], cwd=cwd)

    def remotes(self, cwd: str) -> str:
        try:
            return self.run(["remote"], cwd=cwd).strip()
        except DraftError:
            return ""


def exclude_cursor_cli(clone: Path) -> None:
    info = clone / ".git" / "info"
    info.mkdir(parents=True, exist_ok=True)
    path = info / "exclude"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if ".cursor/" not in text:
        path.write_text(text.rstrip() + "\n" + CURSOR_EXCLUDE, encoding="utf-8")
