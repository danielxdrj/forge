"""Indexa os 5 repositórios allowlistados com Graphify offline e um lock de exclusão.

`graphify extract <clone> --code-only --out <dir>` + `GRAPHIFY_BACKEND=none`. Sem token no env.
Sem release, cai no HEAD da branch padrão. O poll e o botão do owner não correm ao mesmo tempo:
o segundo pedido devolve o progresso (sem HTTP 409).
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
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..draft.envfilter import GH_ENV_ALLOW, filter_env
from ..draft.github_gh import DraftError, GhCli
from ..errors import ForgeError
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository
from . import store

log = logging.getLogger("forge_core.graphs")

EXTRACT_TIMEOUT = 1800
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


def _graph_error(reason: str) -> GraphError:
    """Converte motivo do arquivo (`schema:missing_nodes`) em GraphError."""
    if reason.startswith("schema:"):
        return GraphError("schema", hint=reason.split(":", 1)[1])
    return GraphError(reason)


@dataclass(frozen=True)
class GraphRef:
    kind: str
    ref: str
    tag: str | None
    commit: str


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
        self._progress_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy = False
        self._progress: dict = {"state": "idle", "reason": "", "repos": []}

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
            if meta.get("tag") or meta.get("commit") or meta.get("ref") or meta.get("source"):
                nodes, edges = store.graph_counts(self._root, full)
            out.append({
                "repo": full,
                "tag": meta.get("tag") or None,
                "ref": meta.get("ref") or meta.get("tag") or None,
                "source": meta.get("source") or None,
                "commit": meta.get("commit") or None,
                "indexed_at": meta.get("indexed_at") or None,
                "status": meta.get("status") or None,
                "nodes": int(meta.get("nodes") or nodes or 0),
                "edges": int(meta.get("edges") or edges or 0),
                "error": meta.get("error") or None,
            })
        return out

    def progress(self) -> dict:
        with self._progress_lock:
            repos = [dict(row) for row in self._progress.get("repos") or []]
            state = self._progress.get("state") or "idle"
            reason = self._progress.get("reason") or ""
        busy = self._busy or self._lock.locked()
        if busy and state != "running":
            state = "running"
        return {"state": state, "busy": busy, "reason": reason, "repos": repos}

    def query(self, repo: str, question: str) -> dict:
        full = self._require_repo(repo)
        meta = store.read_meta(self._root, full)
        if meta is None:
            raise GraphError("not_indexed")
        nodes = store.query_nodes(self._root, full, question)
        return {"repo": full, "query": (question or "").strip()[: store.QUERY_MAX], "nodes": nodes}

    def refresh(self, repo: str | None = None, *, reason: str = "manual") -> dict:
        """Reindexa (bloqueante). Se já houver corrida, devolve o progresso — sem `busy`."""
        target = self._require_repo(repo) if repo else None
        if not self._lock.acquire(blocking=False):
            return self._busy_payload()
        self._busy = True
        self._begin_progress(target, reason)
        try:
            return self._run(target, reason)
        finally:
            self._finish()

    def request_refresh(self, repo: str | None = None, *, reason: str = "manual") -> dict:
        """Inicia em segundo plano ou devolve o progresso atual. Nunca levanta `busy`."""
        target = self._require_repo(repo) if repo else None
        if not self._lock.acquire(blocking=False):
            return self._busy_payload()
        self._busy = True
        self._begin_progress(target, reason)
        thread = threading.Thread(
            target=self._run_in_thread, args=(target, reason),
            name="forge-graph-refresh", daemon=True,
        )
        thread.start()
        payload = self.progress()
        payload["accepted"] = True
        return payload

    def _run_in_thread(self, repo: str | None, reason: str) -> None:
        try:
            self._run(repo, reason)
        except GraphError as exc:
            log.info("graph.refresh result=error:%s", exc.code)
            if repo:
                self._record_error(repo, exc.code, exc.hint)
                self._set_progress(repo, "error", error=exc.code, hint=exc.hint or None)
        except Exception:
            log.info("graph.refresh result=error:internal")
        finally:
            self._finish()

    def _busy_payload(self) -> dict:
        payload = self.progress()
        payload["busy"] = True
        payload["state"] = "running"
        payload["accepted"] = False
        return payload

    def _begin_progress(self, repo: str | None, reason: str) -> None:
        if repo:
            targets = [repo]
        else:
            targets = [f"{row.owner}/{row.repo_name}" for row in list_active_allowed_repos(self._repo)]
        with self._progress_lock:
            self._progress = {
                "state": "running",
                "reason": reason,
                "repos": [{"repo": name, "status": "queued"} for name in targets],
            }

    def _set_progress(self, repo: str, status: str, **extra) -> None:
        with self._progress_lock:
            for row in self._progress.get("repos") or []:
                if row.get("repo") == repo:
                    row["status"] = status
                    for key, value in extra.items():
                        if value is not None:
                            row[key] = value
                        elif key in row:
                            row.pop(key, None)
                    break

    def _finish(self) -> None:
        with self._progress_lock:
            if self._progress.get("state") == "running":
                self._progress["state"] = "idle"
        self._busy = False
        try:
            self._lock.release()
        except RuntimeError:
            pass

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

    def _run(self, repo: str | None, reason: str) -> dict:
        force = reason == "manual"
        log.info("graph.refresh reason=%s", reason)
        if repo:
            targets = [repo]
        else:
            targets = [f"{row.owner}/{row.repo_name}" for row in list_active_allowed_repos(self._repo)]
        results = []
        for full in targets:
            try:
                results.append(self._refresh_one(full, force=force))
            except GraphError as exc:
                self._record_error(full, exc.code, exc.hint)
                self._set_progress(full, "error", error=exc.code, hint=exc.hint or None)
                row = {"repo": full, "status": "error", "error": exc.code}
                if exc.hint:
                    row["hint"] = exc.hint
                results.append(row)
        return {"state": "idle", "busy": False, "reason": reason, "repos": results}

    def _refresh_one(self, repo: str, *, force: bool) -> dict:
        self._set_progress(repo, "running")
        source = self._resolve_ref(repo)
        meta = store.read_meta(self._root, repo) or {}
        if not force and self._unchanged(meta, source, repo):
            log.info("graph.index repo=%s ref=%s result=unchanged", repo, source.ref)
            row = {
                "repo": repo, "status": "unchanged", "tag": source.tag,
                "ref": source.ref, "source": source.kind, "commit": source.commit or meta.get("commit"),
            }
            self._set_progress(repo, "unchanged", tag=source.tag, ref=source.ref, commit=row["commit"])
            return row
        clone = None
        try:
            clone = self._clone(repo, source.ref)
            dest = self._extract_to_volume(clone, repo)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            nodes, edges = store.graph_counts(self._root, repo)
            commit = source.commit or self._commit_of(clone)
            if not commit:
                commit = self._commit_of(clone)
            if nodes <= 0:
                raise GraphError("schema", hint="empty_nodes")
            payload = {
                "repo": repo,
                "tag": source.tag,
                "ref": source.ref,
                "source": source.kind,
                "commit": commit,
                "indexed_at": self._now(),
                "nodes": nodes,
                "edges": edges,
                "graph_sha256": digest,
                "status": "ok",
                "error": None,
            }
            store.write_meta(self._root, repo, payload)
            log.info(
                "graph.index repo=%s ref=%s hash=%s nodes=%s edges=%s result=ok",
                repo, source.ref, digest[:16], nodes, edges,
            )
            row = {
                "repo": repo, "status": "ok", "tag": source.tag, "ref": source.ref,
                "source": source.kind, "nodes": nodes, "edges": edges, "commit": commit,
            }
            self._set_progress(repo, "done", tag=source.tag, ref=source.ref, commit=commit)
            return row
        finally:
            if clone is not None:
                shutil.rmtree(clone.parent, ignore_errors=True)

    def _unchanged(self, meta: dict, source: GraphRef, repo: str) -> bool:
        if (meta.get("status") or "") != "ok":
            return False
        if meta.get("error"):
            return False
        if int(meta.get("nodes") or 0) <= 0:
            return False
        if not store.has_valid_indexed_graph(self._root, repo):
            return False
        if source.kind == "release":
            return bool(source.tag) and meta.get("tag") == source.tag
        return bool(source.commit) and meta.get("commit") == source.commit and meta.get("source") == "head"

    def _resolve_ref(self, repo: str) -> GraphRef:
        if self._gh is None:
            raise GraphError("gh_missing")
        try:
            tag = self._gh.latest_release_tag(repo)
            return GraphRef("release", tag, tag, "")
        except DraftError as exc:
            if exc.code != "no_release":
                if exc.code in {"gh_missing", "gh_not_logged", "gh_error", "timeout"}:
                    raise GraphError(exc.code) from exc
                raise GraphError("gh_error") from exc
        try:
            branch, sha = self._gh.default_branch_head(repo)
        except DraftError as exc:
            if exc.code in {"gh_missing", "gh_not_logged", "gh_error", "timeout"}:
                raise GraphError(exc.code) from exc
            raise GraphError("gh_error") from exc
        return GraphRef("head", branch, None, sha)

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

    def _extract_to_volume(self, clone: Path, repo: str) -> Path:
        out_root = clone.parent / "gf-out"
        out_root.mkdir(parents=True, exist_ok=True)
        argv = [
            self._settings.graphify_bin, "extract", str(clone),
            "--code-only", "--out", str(out_root),
        ]
        env = filter_env(os.environ, GRAPHIFY_ENV_ALLOW)
        env["GRAPHIFY_BACKEND"] = "none"
        env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
        env["GRAPHIFY_OUT"] = str(out_root)
        run = self._runner or subprocess.run
        timeout = int(self._settings.graph_extract_timeout or EXTRACT_TIMEOUT)
        try:
            proc = run(
                argv, cwd=str(clone), env=env, capture_output=True, check=False,
                shell=False, timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise GraphError("graphify_missing") from exc
        except subprocess.TimeoutExpired as exc:
            raise GraphError("timeout", hint=f"seconds={timeout}") from exc
        found = store.locate_graph_json(out_root, clone)
        if found is None:
            if proc.returncode != 0:
                raise GraphError("extract_failed", hint=f"exit_code={proc.returncode}")
            raise GraphError("missing_output")
        reason = store.inspect_graph_file(found)
        if reason:
            size = 0
            try:
                size = found.stat().st_size
            except OSError:
                pass
            if reason == "too_large":
                log.info("graph.index repo=%s result=error:too_large bytes=%s", repo, size)
            raise _graph_error(reason)
        try:
            dest = store.copy_graph(found, self._root, repo)
        except store.GraphFileError as exc:
            raise _graph_error(exc.code) from exc
        except OSError:
            raise GraphError("extract_failed", hint="write_failed") from None
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        log.info("graph.extract path=%s hash=%s", "graph.json", digest[:16])
        return dest

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

    def _record_error(self, repo: str, code: str, hint: str = "") -> None:
        meta = store.read_meta(self._root, repo) or {"repo": repo}
        reason = f"{code}:{hint}" if code == "schema" and hint else code
        meta["status"] = "error"
        meta["error"] = reason
        if hint:
            meta["error_hint"] = hint
        else:
            meta.pop("error_hint", None)
        try:
            store.write_meta(self._root, repo, meta)
        except OSError:
            pass
        if code == "schema" and hint:
            log.info("graph.index repo=%s result=error:schema:%s", repo, hint)
        elif code == "timeout":
            extra = f" {hint}" if hint else ""
            log.info("graph.index repo=%s result=error:timeout%s", repo, extra)
        elif hint:
            log.info("graph.index repo=%s result=error:%s detail=%s", repo, code, hint)
        else:
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
