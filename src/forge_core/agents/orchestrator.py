"""Orchestrator (ADR-011): verifica se a tarefa está pronta, escolhe o agente, despacha e registra.

Fluxo de dispatch: automação ligada (settings, ou o ambiente se não houver settings) -> tarefa pronta ->
agente designado, registrado e ativo -> política de aprovação -> pending→in_progress -> executa ->
grava agent_runs -> in_validation (sucesso) ou blocked (falha, erro, timeout, cancelamento). `done`
continua sendo humano. Agente privilegiado NUNCA executa: não há autenticação de aprovadores (ADR-011).
Toda recusa e todo despacho vão para o audit_log; o resumo do resultado NÃO vai para a auditoria.
"""
from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timezone

from ..config import Settings, load_settings, require_automation_enabled
from ..errors import (AgentError, ApprovalError, AuthenticationError, AuthorizationError, DispatchRefusedError,
                      JobFailure, TaskConflictError, TaskRuleError)
from ..logging import redact
from ..storage.sql import SqlRepository
from ..tasks import TaskService
from ..tasks.model import AssigneeKind, Task, TaskStatus as S
from ..auth.store import AuthStore
from .approval import DISABLED, NEEDS_APPROVAL, PRIVILEGED_DISABLED_MESSAGE, ApprovalLedger, decide
from .registry import AgentRegistry
from .runtime import RunResult
from .sandbox import IsolatedRuntime, default_runtime
from .spec import AgentContext, AgentOutcome

ORCHESTRATOR_ACTOR = "agente:orchestrator"
JOB_KIND = "orchestrate"


@dataclass(frozen=True)
class DispatchResult:
    run_id: str
    agent: str
    run_status: str
    task_status: str
    outcome: AgentOutcome | None
    error: str | None


def _clean(value: Any) -> Any:
    """Redige strings aninhadas de usage, mantendo números e a estrutura JSON válida."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(str(k)): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


class Orchestrator:
    def __init__(self, repo: SqlRepository, registry: AgentRegistry, tasks: TaskService | None = None,
                 settings: Settings | None = None, runtime: IsolatedRuntime | None = None,
                 clock: Callable[[], datetime] | None = None):
        self._repo, self._registry, self._settings = repo, registry, settings
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._tasks = tasks or TaskService(repo, self._clock)
        self._runtime = runtime or default_runtime(settings)
        if not isinstance(self._runtime, IsolatedRuntime):
            raise TypeError("Orchestrator exige runtime isolado (FRG-6, ADR-013); execução em thread não é público")
        self.approvals = ApprovalLedger(repo, self._clock)

    def _effective_settings(self) -> Settings:
        """Sem settings explícitas, lê o ambiente como o start() (falha fechada se a config for inválida)."""
        return self._settings if self._settings is not None else load_settings()

    def _refuse(self, actor: str, task_id: str, action: str, message: str) -> None:
        self._repo.record_audit(actor, action, f"task:{task_id}", f"error: {message}")
        raise DispatchRefusedError(message)

    def _agent_active(self, name: str, settings: Settings) -> bool:
        agent = self._registry.get(name)
        return agent is not None and agent.spec.active and name not in settings.agents_disabled

    # --- aprovação (registra o ator informado; NÃO autentica: ADR-011) ---

    def grant_approval(self, task_id: str, approver, agent: str | None = None) -> None:
        """Concede aprovação a um Principal com papel `approver` (ADR-014). Texto não concede nada.

        Não libera execução de agente privilegiado por si: `decide` segue fechado (ADR-011).
        """
        task = self._tasks.get_task(task_id)
        if task is None:
            raise ApprovalError(f"tarefa inexistente: {task_id}")
        self.approvals.grant(task_id, approver, agent or task.assignee_id or "")

    # --- despacho ---

    def dispatch(self, task_id: str, actor, cancel_event: threading.Event | None = None) -> DispatchResult:
        """Despacha como pessoa autenticada com papel `editor` (ADR-014). Texto e objetos do chamador não valem.

        Sem sessão e papel ativos, nada muda de status e nada é executado.
        """
        principal = AuthStore(self._repo).require(actor, "editor")
        requested_by = principal.identity_id
        settings = self._effective_settings()
        require_automation_enabled(settings)
        task = self._tasks.get_task(task_id)
        if task is None:
            self._refuse(requested_by, task_id, "agent.dispatch", "tarefa inexistente")
        if task.status != S.PENDING:
            self._refuse(requested_by, task_id, "agent.dispatch", f"tarefa não está pronta: status {task.status}")
        if not self._tasks.is_ready(task_id):
            self._refuse(requested_by, task_id, "agent.dispatch", "tarefa não está pronta: dependências obrigatórias pendentes")
        if task.assignee_kind != AssigneeKind.AGENT or not task.assignee_id:
            self._refuse(requested_by, task_id, "agent.dispatch", "tarefa sem agente designado")
        name = task.assignee_id
        agent = self._registry.get(name)
        if agent is None:
            self._refuse(requested_by, task_id, "agent.dispatch", f"agente não registrado: {name}")
        if not self._agent_active(name, settings):
            self._refuse(requested_by, task_id, "agent.dispatch", f"agente desativado: {name}")
        decision = decide(agent.spec, approved=self.approvals.available(task_id, name) > 0)
        if decision == NEEDS_APPROVAL:
            self._refuse(requested_by, task_id, "agent.dispatch", f"aprovação pendente para o agente {name}")
        if decision == DISABLED:
            self._refuse(requested_by, task_id, "agent.dispatch", PRIVILEGED_DISABLED_MESSAGE)
        try:  # mesmo gate que o runtime aplica ao executar (defesa em profundidade)
            self._runtime.check_allowed(agent)
        except AgentError as exc:
            self._refuse(requested_by, task_id, "agent.dispatch", str(exc))

        try:  # a mudança de status é o desempate entre despachos concorrentes
            self._tasks.change_status(task_id, S.IN_PROGRESS, principal, expected_version=task.version)
        except (TaskRuleError, TaskConflictError, AuthorizationError, AuthenticationError) as exc:
            self._refuse(requested_by, task_id, "agent.dispatch", f"não foi possível iniciar: {exc}")
        self._repo.record_audit(requested_by, "agent.dispatch", f"task:{task_id}", f"ok: agent={name}")

        ctx = AgentContext(task=self._tasks.get_task(task_id), actor=f"agente:{name}",
                           cancel_event=cancel_event or threading.Event())
        run = self._runtime.execute(agent, ctx)
        run_id = self._record_run(task_id, name, ctx.actor, run)

        target = S.IN_VALIDATION if run.status == "success" else S.BLOCKED
        try:
            self._tasks.change_status(task_id, target, principal)
        except (TaskRuleError, TaskConflictError, AuthorizationError, AuthenticationError) as exc:  # ex.: a tarefa foi cancelada durante a execução
            self._repo.record_audit(ORCHESTRATOR_ACTOR, "agent.result", f"task:{task_id}",
                                    f"error: status não atualizado ({type(exc).__name__}) run={run_id}")
        final = self._tasks.get_task(task_id)
        return DispatchResult(run_id, name, run.status, final.status, run.outcome, run.error)

    def _record_run(self, task_id: str, name: str, actor: str, run: RunResult) -> str:
        run_id, now = str(uuid.uuid4()), self._clock().isoformat()
        o = run.outcome
        usage = json.dumps(_clean(o.usage)) if o and o.usage is not None else None
        with self._repo.transaction() as tx:
            tx.execute(
                "INSERT INTO agent_runs (id, task_id, agent, status, actor, started_at, finished_at, summary, "
                "artifacts, pending, logs, usage, cost, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, task_id, name, run.status, actor, run.started_at, run.finished_at,
                 redact(o.summary) if o else None,
                 json.dumps([redact(str(a)) for a in o.artifacts]) if o else "[]",
                 json.dumps([redact(str(p)) for p in o.pending]) if o else "[]",
                 json.dumps(run.logs), usage, o.cost if o else None,
                 redact(run.error) if run.error else None))
            tx.execute(
                "INSERT INTO task_changes (task_id, field, old_value, new_value, actor, at) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, "agent_run", None, f"{run_id}:{run.status}", ORCHESTRATOR_ACTOR, now))
            tx.audit(ORCHESTRATOR_ACTOR, "agent.result", f"task:{task_id}", f"{run.status}: agent={name} run={run_id}")
        return run_id

    # --- divisão em subtarefas: o orquestrador só propõe ---

    def propose_split(self, task_id: str, requested_by: str = ORCHESTRATOR_ACTOR) -> list[str]:
        """Pede ao agente designado uma proposta. Não cria nada; aplicar exige `apply_split` por uma pessoa."""
        task = self._tasks.get_task(task_id)
        if task is None:
            self._refuse(requested_by, task_id, "orchestrator.split_proposed", "tarefa inexistente")
        agent = self._registry.get(task.assignee_id or "")
        proposer = getattr(agent, "propose_split", None)
        titles = list(proposer(task)) if proposer else []
        self._repo.record_audit(requested_by, "orchestrator.split_proposed", f"task:{task_id}", f"ok: n={len(titles)}")
        return titles

    def apply_split(self, task_id: str, titles: list[str], actor) -> list[Task]:
        """Aplica a divisão como uma pessoa autenticada com papel `editor` (o TaskService confere)."""
        principal = AuthStore(self._repo).require(actor, "editor")
        created = [self._tasks.create_task(t, principal, parent_id=task_id) for t in titles]
        self._repo.record_audit(principal.identity_id, "orchestrator.split_applied",
                                f"task:{task_id}", f"ok: n={len(created)}")
        return created

    def enqueue(self, queue, task_id: str, actor):
        """Enfileira um despacho autorizado. O job guarda só o id do pedido, nunca token ou OAuth.

        A pessoa precisa ser `editor` na seção serializada. A execução revalida papel, sessão e versão.
        """
        auth = AuthStore(self._repo)
        principal = auth.require(actor, "editor")
        requested_by = principal.identity_id
        task = self._tasks.get_task(task_id)
        if task is None:
            self._refuse(requested_by, task_id, "agent.enqueue", "tarefa inexistente")
        dispatch_id = uuid.uuid4().hex
        lock = " FOR UPDATE" if self._repo.dialect != "sqlite" else ""
        version = None
        with auth.authorized(principal, "editor") as tx:
            rows = tx.execute(f"SELECT version FROM tasks WHERE id = ?{lock}", (task_id,)).fetchall()
            if rows:
                version = rows[0][0]
                tx.execute(
                    "INSERT INTO dispatch_requests (id, task_id, task_version, identity_id, requested_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (dispatch_id, task_id, version, requested_by, self._clock().isoformat()))
                tx.audit(requested_by, "agent.enqueue", f"task:{task_id}", f"ok: version={version}")
        if version is None:
            self._refuse(requested_by, task_id, "agent.enqueue", "tarefa inexistente")
        return queue.enqueue(
            JOB_KIND, {"dispatch_id": dispatch_id, "task_id": task_id},
            requested_by, idempotency_key=f"orchestrate:{task_id}:{version}")

    def job_handler(self):
        """Handler da fila: revalida o vínculo e o papel vivo, despacha, revoga a sessão temporária."""
        def handle(job) -> None:
            payload = job.payload if isinstance(job.payload, dict) else {}
            dispatch_id, task_id = payload.get("dispatch_id"), payload.get("task_id")
            if not isinstance(dispatch_id, str) or not isinstance(task_id, str) or not dispatch_id or not task_id:
                raise JobFailure("despacho recusado: payload", retryable=False)
            rows = self._repo.fetch(
                "SELECT task_id, task_version FROM dispatch_requests WHERE id = ?", (dispatch_id,))
            if len(rows) != 1 or rows[0][0] != task_id:
                raise JobFailure("despacho recusado: vinculo", retryable=False)
            expected_version = rows[0][1]
            task = self._tasks.get_task(task_id)
            if task is None or task.version != expected_version:
                raise JobFailure("despacho recusado: versao", retryable=False)
            auth = AuthStore(self._repo)
            principal = None
            try:
                principal = auth.principal_for_dispatch(dispatch_id)
                self.dispatch(task_id, principal)
            except (AuthenticationError, AuthorizationError, DispatchRefusedError, ApprovalError) as exc:
                raise JobFailure(f"despacho recusado: {exc}", retryable=False) from None
            finally:
                if principal is not None:
                    try:
                        auth.revoke_session(principal)
                    except AuthenticationError:
                        pass
        return handle

    handler = job_handler  # nome antigo da FRG-24; mesmo contrato
