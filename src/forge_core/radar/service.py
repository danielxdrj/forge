"""Radar de prioridades: rodada, histórico e registro como agente da aba Agentes.

Fluxo de uma rodada (agendada ou manual):
1. lê os itens abertos do board Backlog de TI via `gh` (somente leitura);
2. pontua com `scoring.analyze` (regra fixa, auditável);
3. pede ao motor um resumo curto do topo. Se o motor falhar, o relatório sai mesmo
   assim, sem resumo: a ordem nunca depende da IA;
4. grava o relatório em `radar_reports` (append-only) e uma execução em `agent_executions`.

Nada é escrito no GitHub. O prompt leva só chave, título, campos do board e motivos,
já com segredos mascarados.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..agent_catalog.service import EXECUTION_COLUMNS, usage_columns
from ..auth.store import AuthStore, Principal
from ..config import Settings
from ..draft.claude_cli import READONLY_DISALLOWED_TOOLS, ClaudeCliAdapter
from ..draft.engine import select_engine_adapter
from ..draft.github_gh import GhCli
from ..errors import AuthorizationError, DraftError, ForgeError
from ..logging import redact
from ..redaction import redact_secrets
from ..storage.seed import list_active_allowed_repos
from ..storage.sql import SqlRepository
from .scoring import analyze

log = logging.getLogger("forge.radar")

AGENT_NAME = "Radar de prioridades"
AGENT_DESCRIPTION = (
    "Lê o board Backlog de TI e aponta o que concluir já, o que está parado e o que vale investigar."
)
HISTORY_LIMIT = 30
MAX_SUMMARY_BYTES = 6 * 1024
SUMMARY_INSTRUCTION = """Você resume o radar de prioridades do Backlog de TI para quem coordena a equipe.
Use só os dados abaixo; não invente issues, números nem datas.
Escreva em português, de 3 a 5 tópicos curtos começando com "- ".
Diga o que concluir primeiro e por quê, e o que está travando o backlog.
Cite as issues pela chave (ex.: repo#123). Sem introdução e sem conclusão."""


class RadarError(ForgeError):
    """Código fixo; nunca inclui segredo."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


def _require_editor_or_owner(store: AuthStore, principal: Principal) -> None:
    store.require_session(principal)
    ident = principal.identity_id
    if store.has_role(ident, "editor") or store.has_role(ident, "owner"):
        return
    store._repo.record_audit(ident, "auth.denied", "role:radar", "error: forbidden")
    raise AuthorizationError("forbidden")


class RadarService:
    def __init__(
        self,
        repo: SqlRepository,
        store: AuthStore,
        settings: Settings,
        *,
        gh: GhCli | None = None,
        provider=None,
        clock: Callable[[], datetime] | None = None,
        env=None,
    ):
        self._repo = repo
        self._store = store
        self._settings = settings
        self._gh = gh
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._env = env
        self._lock = threading.Lock()
        self._busy = False
        self._last_error = ""

    # --- leitura ---

    @property
    def busy(self) -> bool:
        return self._busy

    def overview(self, principal: Principal) -> dict:
        _require_editor_or_owner(self._store, principal)
        latest = self._reports(limit=1)
        return {
            "busy": self._busy,
            "schedule": list(self._settings.radar_times),
            "timezone": self._settings.radar_timezone,
            "next_run": next_run(self._clock(), self._settings.radar_times, self._settings.radar_timezone),
            "stale_days": self._settings.radar_stale_days,
            "last_error": self._last_error,
            "latest": latest[0] if latest else None,
        }

    def history(self, principal: Principal) -> list[dict]:
        _require_editor_or_owner(self._store, principal)
        out = []
        for report in self._reports(limit=HISTORY_LIMIT):
            out.append({
                "id": report["id"],
                "created_at": report["created_at"],
                "reason": report["reason"],
                "status": report["status"],
                "stats": report.get("stats") or {},
            })
        return out

    def get(self, principal: Principal, report_id: str) -> dict:
        _require_editor_or_owner(self._store, principal)
        rows = self._repo.fetch(
            "SELECT id, created_at, reason, status, error_code, summary, payload, created_by "
            "FROM radar_reports WHERE id = ?",
            (report_id,),
        )
        if not rows:
            raise RadarError("not_found")
        return _report_from_row(rows[0])

    # --- rodada ---

    def start_manual(self, principal: Principal) -> dict:
        """Dispara uma rodada em segundo plano. A tela acompanha por `overview`."""
        _require_editor_or_owner(self._store, principal)
        if self._gh is None:
            raise RadarError("gh_missing")
        if not self._lock.acquire(blocking=False):
            raise RadarError("busy")
        self._busy = True
        thread = threading.Thread(
            target=self._run_locked, args=("manual", principal.identity_id), name="forge-radar-manual", daemon=True,
        )
        thread.start()
        return {"state": "running"}

    def run_scheduled(self) -> dict | None:
        """Rodada da agenda. Se já houver uma em andamento, pula esta."""
        if not self._lock.acquire(blocking=False):
            log.info("radar.schedule result=skip:busy")
            return None
        self._busy = True
        return self._run_locked("schedule", "sistema:radar")

    def run_now(self, reason: str, actor: str) -> dict:
        """Rodada síncrona (testes e CLI)."""
        if not self._lock.acquire(blocking=False):
            raise RadarError("busy")
        self._busy = True
        return self._run_locked(reason, actor)

    def _run_locked(self, reason: str, actor: str) -> dict:
        started = time.monotonic()
        started_at = self._clock().isoformat()
        report = None
        try:
            report = self._run(reason, actor)
            self._last_error = "" if report["status"] == "ok" else report["error"]
            return report
        finally:
            if report is not None:
                duration_ms = int((time.monotonic() - started) * 1000)
                try:
                    self._record_execution(report, started_at, duration_ms)
                except Exception as exc:  # noqa: BLE001 - registro na aba Agentes não pode derrubar a rodada
                    log.info("radar.execution result=error:%s", getattr(exc, "code", "internal"))
            self._busy = False
            self._lock.release()

    def _run(self, reason: str, actor: str) -> dict:
        now = self._clock()
        report_id = str(uuid.uuid4())
        try:
            if self._gh is None:
                raise RadarError("gh_missing")
            items = self._gh.list_open_project_items()
        except (DraftError, RadarError) as exc:
            code = getattr(exc, "code", "gh_error")
            self._save(report_id, now, reason, "error", code, "", {}, actor)
            log.info("radar.run reason=%s result=error:%s", reason, code)
            return self._load(report_id)
        allowed = {f"{r.owner}/{r.repo_name}".lower() for r in list_active_allowed_repos(self._repo)}
        result = analyze(items, now=now, stale_days=self._settings.radar_stale_days, allowed_repos=allowed)
        summary, summary_error, usage, cost = self._summary(result)
        payload = {
            **result, "stale_days": self._settings.radar_stale_days, "summary_error": summary_error,
            "usage": {**usage, "cost_usd": cost} if (usage or cost is not None) else {},
        }
        self._save(report_id, now, reason, "ok", "", summary, payload, actor)
        log.info("radar.run reason=%s result=ok open=%s now=%s", reason, result["stats"]["open"], result["stats"]["now"])
        return self._load(report_id)

    def _summary(self, result: dict) -> tuple[str, str, dict, float | None]:
        """Resumo do motor + uso da chamada (tokens e custo estimado), quando o motor informa."""
        if not result["now"] and not result["stale"]:
            return "", "", {}, None
        lines = [SUMMARY_INSTRUCTION, "", "## Números", json.dumps(result["stats"], ensure_ascii=False)]
        for title, key in (("Concluir agora", "now"), ("Paradas", "stale"), ("Vale investigar", "investigate")):
            if not result[key]:
                continue
            lines.append(f"\n## {title}")
            for entry in result[key]:
                why = "; ".join(entry["reasons"] + entry.get("investigate_reasons", []))
                lines.append(
                    f"- {entry['key']} [{entry['status'] or 'sem status'}, {entry['prioridade'] or 'sem prioridade'}] "
                    f"{entry['title']} — {why}"
                )
        prompt = redact_secrets("\n".join(lines))
        if "FORGE_" in prompt or "GH_TOKEN" in prompt or "GITHUB_TOKEN" in prompt:
            return "", "secret_in_prompt", {}, None
        try:
            response = self._adapter().complete(prompt)
        except DraftError as exc:
            return "", exc.code, {}, None
        except Exception:  # noqa: BLE001 - o relatório sai sem resumo; a ordem não depende da IA
            return "", "provider_error", {}, None
        text = redact_secrets(response.text or "").strip()
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_SUMMARY_BYTES:
            text = encoded[:MAX_SUMMARY_BYTES].decode("utf-8", "ignore")
        usage = dict(getattr(response, "usage", None) or {})
        return text, "", usage, getattr(response, "cost", None)

    def _adapter(self):
        if self._provider is not None:
            return self._provider
        env = self._env or os.environ
        timeout = int(env.get("FORGE_CLAUDE_TIMEOUT", "120") or 120)
        adapter = select_engine_adapter(env, timeout=timeout)
        if isinstance(adapter, ClaudeCliAdapter):
            adapter.permission_mode = "plan"
            adapter.disallowed_tools = READONLY_DISALLOWED_TOOLS
            adapter.max_turns = 2
        return adapter

    # --- persistência ---

    def _save(self, report_id, now, reason, status, error_code, summary, payload, actor) -> None:
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO radar_reports (id, created_at, reason, status, error_code, summary, payload, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (report_id, now.isoformat(), reason, status, error_code, summary,
                 json.dumps(payload, ensure_ascii=False), actor),
            )
            stats = (payload or {}).get("stats") or {}
            tx.audit(
                actor, "radar.run", f"radar:{report_id}",
                f"{'ok' if status == 'ok' else 'error: ' + error_code}: reason={reason} "
                f"open={stats.get('open', 0)} now={stats.get('now', 0)}",
            )

    def _load(self, report_id: str) -> dict:
        rows = self._repo.fetch(
            "SELECT id, created_at, reason, status, error_code, summary, payload, created_by "
            "FROM radar_reports WHERE id = ?",
            (report_id,),
        )
        return _report_from_row(rows[0])

    def _reports(self, limit: int) -> list[dict]:
        rows = self._repo.fetch(
            "SELECT id, created_at, reason, status, error_code, summary, payload, created_by "
            "FROM radar_reports ORDER BY created_at DESC, id LIMIT ?",
            (int(limit),),
        )
        return [_report_from_row(r) for r in rows]

    def _ensure_agent(self) -> str:
        rows = self._repo.fetch("SELECT id FROM agents WHERE name = ?", (AGENT_NAME,))
        if rows:
            return rows[0][0]
        agent_id = str(uuid.uuid4())
        ts = self._clock().isoformat()
        trigger = "agenda: " + ", ".join(self._settings.radar_times) if self._settings.radar_times else "manual"
        engine = getattr(self._provider, "name", "") or os.environ.get("FORGE_ENGINE", "") or ""
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO agents (id, name, description, scope, status, trigger, engine, "
                "permissions_read, permissions_write, permissions_denied, created_at, updated_at) "
                "VALUES (?, ?, ?, 'development', 'active', ?, ?, ?, '[]', ?, ?, ?)",
                (
                    agent_id, AGENT_NAME, AGENT_DESCRIPTION, trigger, engine,
                    json.dumps(["board Backlog de TI", "issues"], ensure_ascii=False),
                    json.dumps(["banco de dados", "FTP", "Portainer"], ensure_ascii=False),
                    ts, ts,
                ),
            )
            tx.audit("sistema:radar", "agent.register", f"agent:{agent_id}", "ok: radar")
        return agent_id

    def _record_execution(self, report: dict, started_at: str, duration_ms: int) -> None:
        agent_id = self._ensure_agent()
        stats = report.get("stats") or {}
        if report["status"] == "ok":
            status = "ok"
            event = (
                f"{stats.get('now', 0)} para concluir já, {stats.get('stale', 0)} paradas, "
                f"{stats.get('open', 0)} abertas"
            )
            log_text = report.get("summary") or ""
        else:
            status = "error"
            event = f"falha: {report.get('error') or 'erro'}"
            log_text = ""
        usage = dict(report.get("usage") or {})
        cost = usage.pop("cost_usd", None)
        with self._repo.transaction() as tx:
            tx.execute(
                f"INSERT INTO agent_executions ({EXECUTION_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), agent_id, started_at, self._clock().isoformat(), status, event,
                 duration_ms, redact(log_text), *usage_columns(usage, cost)),
            )


def _report_from_row(row) -> dict:
    ident, created_at, reason, status, error_code, summary, payload_raw, created_by = row
    try:
        payload = json.loads(payload_raw or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "id": ident,
        "created_at": created_at,
        "reason": reason,
        "status": status,
        "error": error_code or "",
        "summary": summary or "",
        "summary_error": payload.get("summary_error") or "",
        "stats": payload.get("stats") or {},
        "stale_days": payload.get("stale_days"),
        "now": payload.get("now") or [],
        "stale": payload.get("stale") or [],
        "investigate": payload.get("investigate") or [],
        "usage": payload.get("usage") or {},
        "manual": reason == "manual",
        "created_by": created_by if reason == "manual" else "",
    }


def _slots(times: tuple[str, ...]) -> list[tuple[int, int]]:
    out = []
    for item in times:
        hh, _sep, mm = item.partition(":")
        try:
            out.append((int(hh), int(mm)))
        except ValueError:
            continue
    return sorted(out)


def next_run(now: datetime, times: tuple[str, ...], timezone: str) -> str | None:
    """Próximo horário da agenda, em ISO com o fuso local. None se a agenda estiver desligada."""
    slots = _slots(times)
    if not slots:
        return None
    local = now.astimezone(ZoneInfo(timezone))
    for days in range(2):
        day = (local + timedelta(days=days)).date()
        for hh, mm in slots:
            candidate = datetime(day.year, day.month, day.day, hh, mm, tzinfo=local.tzinfo)
            if candidate > local:
                return candidate.isoformat()
    return None


class RadarScheduler:
    """Dispara a rodada nos horários configurados (fuso local). Uma vez por horário por dia.

    Checa a cada `tick_seconds`. Se o servidor subir até `window_minutes` depois do horário,
    a rodada daquele horário ainda acontece; depois disso, espera o próximo.
    """

    def __init__(
        self,
        service: RadarService,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        tick_seconds: float = 30.0,
        window_minutes: int = 10,
    ):
        self._service = service
        self._slots = _slots(settings.radar_times)
        self._tz = ZoneInfo(settings.radar_timezone)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._tick = tick_seconds
        self._window = timedelta(minutes=window_minutes)
        self._done: set[tuple[str, int, int]] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None or not self._slots:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="forge-radar-schedule", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def tick(self) -> bool:
        """Roda se algum horário venceu agora. Devolve True se disparou."""
        local = self._clock().astimezone(self._tz)
        for hh, mm in self._slots:
            key = (local.date().isoformat(), hh, mm)
            if key in self._done:
                continue
            slot = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot <= local < slot + self._window:
                self._done.add(key)
                try:
                    self._service.run_scheduled()
                except Exception as exc:  # noqa: BLE001 - a agenda segue viva para o próximo horário
                    log.info("radar.schedule result=error:%s", getattr(exc, "code", "internal"))
                return True
        return False

    def _loop(self) -> None:
        while not self._stop.wait(self._tick):
            self.tick()
