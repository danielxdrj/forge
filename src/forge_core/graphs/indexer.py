"""Indexa os 5 repositórios allowlistados com Graphify offline e um lock de exclusão.

`graphify extract <clone> --code-only` + `GRAPHIFY_BACKEND=none`. Sem token no env.
O poll e o botão do owner não correm ao mesmo tempo.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from ..config import Settings
from ..draft.envfilter import GH_ENV_ALLOW, filter_env
from ..draft.github_gh import DraftError, GhCli
from ..errors import ForgeError
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository
from . import store

log = logging.getLogger("forge_core.graphs")

EXTRACT_TIMEOUT = 600
GRAPHIFY_ENV_ALLOW = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "TMPDIR", "TMP", "TEMP",
    "LANG", "LC_ALL", "LC_CTYPE",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR",
})
Runner = Callable[..., subprocess.CompletedProcess]


class GraphError(ForgeError):
    """Falha curta do índice. Código fixo; sem stdout/stderr do gh ou do graphify."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


class GraphIndexer:
    def __init__(
        self,
        repo: SqlRepository,
        settings: Settings,
        *,
        gh: GhCli | None = None,
        runner: Runner | None = None,
        clock: Callable[[], str] | None = None,
        on_poll: Callable[[str], None] | None = None,
    ):
        self._repo = repo
        self._settings = settings
        self._gh = gh
        self._runner = runner
        self._clock = clock
        self._on_poll = on_poll
        self._root = Path(settings.graph_dir)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self) -> None:
        """Passo inicial + poll periódico. Idempotente. `poll_seconds=0` só faz o passo inicial."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="forge-graph-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def status(self) -> list[dict]:
        out = []
        for item in list_active_allowed_repos(self._repo):
            full = f"{item.owner}/{item.repo_name}"
            meta = store.read_meta(self._root, full) or {}
            nodes, edges = 0, 0
            if meta.get("tag"):
                nodes, edges = store.graph_counts(self._root, full)
            out.append({
                "repo": full,
                "tag": meta.get("tag") or None,
                "commit": meta.get("commit") or None,
                "indexed_at": meta.get("indexed_at") or None,
                "nodes": int(meta.get("nodes") or nodes or 0),
                "edges": int(meta.get("edges") or edges or 0),
                "error": meta.get("error") or None,
            })
        return out

    def query(self, repo: str, question: str) -> dict:
        full = self._require_repo(repo)
        meta = store.read_meta(self._root, full)
        if meta is None:
            raise GraphError("not_indexed")
        nodes = store.query_nodes(self._root, full, question)
        return {"repo": full, "query": (question or "").strip()[: store.QUERY_MAX], "nodes": nodes}

    def refresh(self, repo: str | None = None, *, reason: str = "manual") -> dict:
        """Reindexa um repo ou todos. Recusa se já houver uma corrida (`busy`)."""
        if not self._lock.acquire(blocking=False):
            raise GraphError("busy")
        self._busy = True
        log.info("graph.refresh reason=%s", reason)
        try:
            force = reason == "manual"
            if repo:
                result = self._refresh_one(self._require_repo(repo), force=force)
                return {"repos": [result]}
            return {"repos": self._refresh_all(force=force)}
        finally:
            self._busy = False
            self._lock.release()

    def _loop(self) -> None:
        try:
            self.refresh(reason="startup")
        except GraphError as exc:
            log.info("graph.poll result=error:%s", exc.code)
        except Exception:
            log.info("graph.poll result=error:internal")
        self._call_on_poll("startup")
        interval = self._settings.graph_poll_seconds
        if interval <= 0:
            return
        while not self._stop.wait(interval):
            try:
                self.refresh(reason="poll")
            except GraphError as exc:
                log.info("graph.poll result=error:%s", exc.code)
            except Exception:
                log.info("graph.poll result=error:internal")
            self._call_on_poll("poll")

    def _call_on_poll(self, reason: str) -> None:
        if self._on_poll is None:
            return
        try:
            self._on_poll(reason)
        except Exception as exc:
            code = getattr(exc, "code", None) or "internal"
            log.info("graph.poll extra=error:%s", code)

    def _refresh_all(self, *, force: bool) -> list[dict]:
        results = []
        for item in list_active_allowed_repos(self._repo):
            full = f"{item.owner}/{item.repo_name}"
            try:
                results.append(self._refresh_one(full, force=force))
            except GraphError as exc:
                self._record_error(full, exc.code)
                results.append({"repo": full, "status": "error", "error": exc.code})
        return results

    def _refresh_one(self, repo: str, *, force: bool) -> dict:
        tag = self._latest_tag(repo)
        meta = store.read_meta(self._root, repo) or {}
        if not force and meta.get("tag") == tag and not meta.get("error"):
            log.info("graph.index repo=%s tag=%s result=unchanged", repo, tag)
            return {"repo": repo, "status": "unchanged", "tag": tag}
        clone = None
        try:
            clone = self._clone(repo, tag)
            graph_src = self._extract(clone)
            try:
                dest = store.copy_graph(graph_src, self._root, repo)
            except (OSError, ValueError) as exc:
                raise GraphError("extract_failed") from exc
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            nodes, edges = store.graph_counts(self._root, repo)
            commit = self._commit_of(clone)
            payload = {
                "repo": repo,
                "tag": tag,
                "commit": commit,
                "indexed_at": self._now(),
                "nodes": nodes,
                "edges": edges,
                "graph_sha256": digest,
                "error": None,
            }
            store.write_meta(self._root, repo, payload)
            log.info(
                "graph.index repo=%s tag=%s hash=%s nodes=%s edges=%s result=ok",
                repo, tag, digest[:16], nodes, edges,
            )
            return {"repo": repo, "status": "ok", "tag": tag, "nodes": nodes, "edges": edges}
        finally:
            if clone is not None:
                shutil.rmtree(clone.parent, ignore_errors=True)

    def _latest_tag(self, repo: str) -> str:
        if self._gh is None:
            raise GraphError("gh_missing")
        try:
            return self._gh.latest_release_tag(repo)
        except DraftError as exc:
            if exc.code in {"no_release", "gh_missing", "gh_not_logged", "gh_error", "timeout"}:
                raise GraphError(exc.code) from exc
            raise GraphError("gh_error") from exc

    def _clone(self, repo: str, tag: str) -> Path:
        if self._gh is None:
            raise GraphError("gh_missing")
        parent = Path(tempfile.mkdtemp(prefix="forge-graphs-"))
        dest = parent / store.slug_for(repo)
        try:
            self._gh.clone_repo_at(repo, str(dest), tag)
        except DraftError as exc:
            raise GraphError("clone_failed") from exc
        if not dest.is_dir():
            raise GraphError("clone_failed")
        return dest

    def _extract(self, clone: Path) -> Path:
        argv = [self._settings.graphify_bin, "extract", str(clone), "--code-only"]
        env = filter_env(os.environ, GRAPHIFY_ENV_ALLOW)
        env["GRAPHIFY_BACKEND"] = "none"
        env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
        run = self._runner or subprocess.run
        try:
            proc = run(
                argv, cwd=str(clone), env=env, capture_output=True, check=False,
                shell=False, timeout=EXTRACT_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise GraphError("graphify_missing") from exc
        except subprocess.TimeoutExpired as exc:
            raise GraphError("timeout") from exc
        if proc.returncode != 0:
            raise GraphError("extract_failed")
        graph = clone / "graphify-out" / "graph.json"
        if not graph.is_file():
            raise GraphError("extract_failed")
        log.info("graph.extract path=%s hash=%s", "graphify-out/graph.json",
                 hashlib.sha256(graph.read_bytes()).hexdigest()[:16])
        return graph

    def _commit_of(self, clone: Path) -> str:
        env = filter_env(os.environ, GH_ENV_ALLOW)
        env["GIT_TERMINAL_PROMPT"] = "0"
        run = self._runner or subprocess.run
        try:
            proc = run(
                ["git", "rev-parse", "HEAD"], cwd=str(clone), env=env,
                capture_output=True, check=False, shell=False, timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        if proc.returncode != 0:
            return ""
        return (proc.stdout or b"").decode("utf-8", "replace").strip()[:64]

    def _record_error(self, repo: str, code: str) -> None:
        meta = store.read_meta(self._root, repo) or {"repo": repo}
        meta["error"] = code
        try:
            store.write_meta(self._root, repo, meta)
        except OSError:
            pass
        log.info("graph.index repo=%s result=error:%s", repo, code)

    def _require_repo(self, repo: str) -> str:
        name = (repo or "").strip()
        allowed = {f"{row.owner}/{row.repo_name}" for row in list_active_allowed_repos(self._repo)}
        match = {item for item in allowed if item.lower() == name.lower()}
        if len(match) != 1:
            raise GraphError("repo_not_allowed")
        return next(iter(match))

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock()
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
