"""Git local no clone temporário. O Forge faz commit/push; o motor não recebe GH_TOKEN."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping

from ..draft.envfilter import filter_env
from ..errors import DraftError

Runner = Callable[..., subprocess.CompletedProcess]
GIT_ENV_ALLOW = frozenset({
    "PATH", "PATHEXT", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "USERNAME", "USER", "OS", "LANG", "LC_ALL", "LC_CTYPE",
    "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
})
DEFAULT_TIMEOUT = 60
MAX_OUTPUT = 256 * 1024


class GitCli:
    def __init__(self, *, env: Mapping[str, str] | None = None, runner: Runner | None = None,
                 timeout: int = DEFAULT_TIMEOUT):
        self._env = env
        self._runner = runner
        self.timeout = timeout
        self.calls: list[list[str]] = []

    def _env_os(self) -> dict[str, str]:
        child = filter_env(self._env or os.environ, GIT_ENV_ALLOW)
        child.setdefault("GIT_TERMINAL_PROMPT", "0")
        return child

    def run(self, args: list[str], *, cwd: str) -> str:
        argv = ["git", *args]
        self.calls.append(argv)
        run = self._runner or subprocess.run
        try:
            proc = run(
                argv, cwd=cwd, env=self._env_os(), capture_output=True, check=False,
                shell=False, timeout=self.timeout,
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

    def status(self, cwd: str) -> str:
        return self.run(["status", "--porcelain"], cwd=cwd)

    def diff(self, cwd: str) -> str:
        staged = self.run(["diff", "--cached"], cwd=cwd)
        work = self.run(["diff"], cwd=cwd)
        if not staged.strip() and not work.strip() and self.status(cwd).strip():
            self.run(["add", "-A"], cwd=cwd)
            return self.run(["diff", "--cached"], cwd=cwd)
        return work or staged

    def diff_stat(self, cwd: str) -> str:
        text = self.run(["diff", "--stat", "HEAD"], cwd=cwd)
        if not text.strip():
            text = self.run(["diff", "--stat", "--cached"], cwd=cwd)
        return text

    def log_one(self, cwd: str) -> str:
        return self.run(["log", "-1", "--oneline"], cwd=cwd)

    def add_all(self, cwd: str) -> None:
        self.run(["add", "-A"], cwd=cwd)

    def has_head(self, cwd: str) -> bool:
        try:
            self.run(["rev-parse", "--verify", "HEAD"], cwd=cwd)
            return True
        except DraftError:
            return False

    def commit(self, cwd: str, message: str) -> None:
        self.run([
            "-c", "user.email=forge@example.invalid",
            "-c", "user.name=Forge",
            "commit", "-m", message,
        ], cwd=cwd)

    def push(self, cwd: str, branch: str) -> None:
        self.run(["push", "-u", "origin", branch], cwd=cwd)

    def ls_files(self, cwd: str) -> list[str]:
        text = self.run(["ls-files"], cwd=cwd)
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
