"""Gerenciamento de tarefas sobre SqlRepository (ADR-010).

Toda mudança grava, na mesma transação: a alteração, o histórico (`task_changes` com valor antigo e
novo; `task_history` com a linha do tempo de status) e a auditoria. Recusas também são auditadas.
Texto da tarefa (título, objetivo etc.) fica guardado como veio e NÃO vai para a auditoria: a
auditoria registra só nomes de campos e status. Não coloque segredos em tarefas.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from ..errors import TaskConflictError, TaskRuleError
from ..logging import redact
from ..storage.sql import SqlRepository
from . import rules
from .model import Dependency, Project, Stage, Task, TaskChange, TaskStatus as S

_COLS = ("id, title, objective, context, scope, acceptance_criteria, priority, status, assignee_kind, "
         "assignee_id, start_date, due_date, completed_at, stage_id, parent_task_id, required, version, "
         "created_at, updated_at")
_EDITABLE = ("title", "objective", "context", "scope", "acceptance_criteria", "priority",
             "assignee_kind", "assignee_id", "start_date", "due_date")
# Chave do advisory lock que serializa mudanças no grafo de dependências (somente PostgreSQL).
_DEPENDENCY_GRAPH_LOCK = 1_650_015_001
_REFUSALS = (TaskRuleError, TaskConflictError, KeyError)


_SAFE_TARGET = re.compile(r"^(\w+):([0-9a-fA-F-]{36}|new)$")


def _safe_target(target: str) -> str:
    """Id vindo do chamador só vai para a auditoria se tiver cara de UUID; senão vira `<tipo>:unknown`."""
    if _SAFE_TARGET.match(target):
        return target
    return target.split(":", 1)[0] + ":unknown"


def _task(row) -> Task:
    r = list(row)
    r[15] = bool(r[15])
    return Task(*r)


def _text(value) -> str | None:
    return None if value is None else str(value)


class TaskService:
    def __init__(self, repo: SqlRepository, clock: Callable[[], datetime] | None = None):
        self._repo = repo
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._after_edges_read: Callable[[], None] | None = None  # gancho de teste (corridas determinísticas)

    def _now(self) -> str:
        return self._clock().isoformat()

    def _lock(self) -> str:
        return " FOR UPDATE" if self._repo.dialect == "postgres" else ""

    def _run(self, action: str, actor: str, target: str, fn):
        """Executa `fn(tx, now)` numa transação; recusas de regra viram auditoria `error:` e relançam."""
        err: Exception | None = None
        result = None
        with self._repo.transaction() as tx:
            try:
                result = fn(tx, self._now())
            except _REFUSALS as exc:
                err = exc
        if err is not None:
            msg = err.args[0] if isinstance(err, KeyError) and err.args else str(err)
            self._repo.record_audit(actor, action, _safe_target(target), f"error: {redact(str(msg))}")
            raise err
        return result

    @staticmethod
    def _change(tx, task_id: str, field: str, old, new, actor: str, now: str) -> None:
        tx.execute(
            "INSERT INTO task_changes (task_id, field, old_value, new_value, actor, at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, field, _text(old), _text(new), actor, now))

    @staticmethod
    def _load(tx, task_id: str, lock: str) -> Task:
        rows = tx.execute(f"SELECT {_COLS} FROM tasks WHERE id = ?{lock}", (task_id,)).fetchall()
        if not rows:
            raise KeyError("tarefa inexistente")
        return _task(rows[0])

    def create_project(self, title: str, actor: str) -> Project:
        def fn(tx, now):
            if not title.strip():
                raise TaskRuleError("título do projeto é obrigatório")
            pid = str(uuid.uuid4())
            tx.execute("INSERT INTO projects (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                       (pid, title, now, now))
            tx.audit(actor, "project.create", f"project:{pid}", "ok")
            return Project(pid, title, now)
        return self._run("project.create", actor, "project:new", fn)

    def create_stage(self, project_id: str, title: str, actor: str) -> Stage:
        def fn(tx, now):
            if not title.strip():
                raise TaskRuleError("título da etapa é obrigatório")
            if not tx.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchall():
                raise KeyError("projeto inexistente")
            sid = str(uuid.uuid4())
            tx.execute("INSERT INTO stages (id, project_id, title, created_at) VALUES (?, ?, ?, ?)",
                       (sid, project_id, title, now))
            tx.audit(actor, "stage.create", f"stage:{sid}", "ok")
            return Stage(sid, project_id, title, now)
        return self._run("stage.create", actor, f"project:{project_id}", fn)

    def list_projects(self) -> list[Project]:
        return [Project(*r) for r in self._repo.fetch("SELECT id, title, created_at FROM projects ORDER BY created_at, id")]

    def list_stages(self, project_id: str) -> list[Stage]:
        rows = self._repo.fetch(
            "SELECT id, project_id, title, created_at FROM stages WHERE project_id = ? ORDER BY created_at, id",
            (project_id,))
        return [Stage(*r) for r in rows]

    def create_task(self, title: str, actor: str, *, objective: str = "", context: str = "", scope: str = "",
                    acceptance_criteria: str = "", priority: str = "normal", status: str = S.PENDING,
                    assignee_kind: str | None = None, assignee_id: str | None = None,
                    start_date: str | None = None, due_date: str | None = None,
                    stage_id: str | None = None, parent_id: str | None = None, required: bool = True) -> Task:
        task_id = str(uuid.uuid4())

        def fn(tx, now):
            rules.validate_fields(title, priority, assignee_kind, assignee_id, start_date, due_date)
            if status not in S.INITIAL:
                raise TaskRuleError(f"status inicial deve ser um de {', '.join(S.INITIAL)}")
            stage = stage_id
            if parent_id:
                parent = self._load(tx, parent_id, "")
                if parent.parent_task_id is not None:
                    raise TaskRuleError("subtarefa não pode ter subtarefas (profundidade máxima 1)")
                if stage_id and stage_id != parent.stage_id:
                    raise TaskRuleError("subtarefa herda a etapa da tarefa pai")
                stage = parent.stage_id
            if stage and not tx.execute("SELECT 1 FROM stages WHERE id = ?", (stage,)).fetchall():
                raise KeyError("etapa inexistente")
            tx.execute(
                f"INSERT INTO tasks ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 1, ?, ?)",
                (task_id, title, objective, context, scope, acceptance_criteria, priority, status,
                 assignee_kind, assignee_id, start_date, due_date, stage, parent_id, int(required), now, now))
            tx.execute("INSERT INTO task_history (task_id, status, actor, at) VALUES (?, ?, ?, ?)",
                       (task_id, status, actor, now))
            self._change(tx, task_id, "status", None, status, actor, now)
            tx.audit(actor, "task.create", f"task:{task_id}", "ok")
        self._run("task.create", actor, "task:new", fn)
        return self.get_task(task_id)  # type: ignore[return-value]

    def update_task(self, task_id: str, actor: str, expected_version: int, **fields) -> Task:
        """Edita campos (não o status). `expected_version` evita sobrescrever mudança de outra pessoa."""
        def fn(tx, now):
            unknown = set(fields) - set(_EDITABLE)
            if unknown:
                raise TaskRuleError(f"campos não editáveis ({len(unknown)})")
            task = self._load(tx, task_id, self._lock())
            if task.version != expected_version:
                raise TaskConflictError("version desatualizada: releia a tarefa")
            if task.status in S.TERMINAL:
                raise TaskRuleError(f"tarefa {task.status} não pode ser editada")
            merged = {f: fields.get(f, getattr(task, f)) for f in _EDITABLE}
            rules.validate_fields(merged["title"], merged["priority"], merged["assignee_kind"],
                                  merged["assignee_id"], merged["start_date"], merged["due_date"])
            changed = [f for f in _EDITABLE if merged[f] != getattr(task, f)]
            if not changed:
                return
            sets = ", ".join(f"{f} = ?" for f in changed)
            cur = tx.execute(
                f"UPDATE tasks SET {sets}, version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                (*[merged[f] for f in changed], now, task_id, expected_version))
            if cur.rowcount != 1:
                raise TaskConflictError("a tarefa mudou durante a edição")
            for f in changed:
                self._change(tx, task_id, f, getattr(task, f), merged[f], actor, now)
            tx.audit(actor, "task.update", f"task:{task_id}", f"ok: fields={','.join(changed)}")
        self._run("task.update", actor, f"task:{task_id}", fn)
        return self.get_task(task_id)  # type: ignore[return-value]

    def change_status(self, task_id: str, new_status: str, actor: str, expected_version: int | None = None) -> Task:
        def fn(tx, now):
            task = self._load(tx, task_id, self._lock())
            if expected_version is not None and task.version != expected_version:
                raise TaskConflictError("version desatualizada: releia a tarefa")
            deps = self._dependency_states(tx, task_id)
            subs = [(i, st, bool(rq)) for i, st, rq in tx.execute(
                "SELECT id, status, required FROM tasks WHERE parent_task_id = ?", (task_id,)).fetchall()]
            rules.check_transition(task.status, new_status, deps, subs)
            cols: dict[str, object] = {"status": new_status}
            if new_status == S.IN_PROGRESS and task.start_date is None:
                cols["start_date"] = self._clock().date().isoformat()
            if new_status == S.DONE:
                cols["completed_at"] = now
            sets = ", ".join(f"{k} = ?" for k in cols)
            cur = tx.execute(
                f"UPDATE tasks SET {sets}, version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                (*cols.values(), now, task_id, task.version))
            if cur.rowcount != 1:
                raise TaskConflictError("a tarefa mudou durante a mudança de status")
            tx.execute("INSERT INTO task_history (task_id, status, actor, at) VALUES (?, ?, ?, ?)",
                       (task_id, new_status, actor, now))
            for field, value in cols.items():
                self._change(tx, task_id, field, getattr(task, field), value, actor, now)
            tx.audit(actor, "task.status", f"task:{task_id}", f"ok: {task.status} -> {new_status}")
        self._run("task.status", actor, f"task:{task_id}", fn)
        return self.get_task(task_id)  # type: ignore[return-value]

    @staticmethod
    def _dependency_states(tx, task_id: str) -> list[rules.State]:
        rows = tx.execute(
            "SELECT t.id, t.status, d.required FROM task_dependencies d JOIN tasks t ON t.id = d.depends_on_id "
            "WHERE d.task_id = ?", (task_id,)).fetchall()
        return [(i, st, bool(rq)) for i, st, rq in rows]

    def add_dependency(self, task_id: str, depends_on_id: str, actor: str, required: bool = True) -> Dependency:
        def fn(tx, now):
            if self._repo.dialect == "postgres":
                # Valida ciclo e insere atomicamente: sem isto, A->B e B->A concorrentes passam as duas.
                # SQLite já serializa por BEGIN IMMEDIATE. O lock cai sozinho no fim da transação.
                tx.execute("SELECT pg_advisory_xact_lock(?)", (_DEPENDENCY_GRAPH_LOCK,))
            task = self._load(tx, task_id, "")
            self._load(tx, depends_on_id, "")
            if task.status in S.TERMINAL:
                raise TaskRuleError(f"tarefa {task.status} não aceita dependências")
            edges: dict[str, set[str]] = {}
            for a, b in tx.execute("SELECT task_id, depends_on_id FROM task_dependencies").fetchall():
                edges.setdefault(a, set()).add(b)
            if self._after_edges_read is not None:
                self._after_edges_read()
            existing = tx.execute(
                "SELECT required FROM task_dependencies WHERE task_id = ? AND depends_on_id = ?",
                (task_id, depends_on_id)).fetchall()
            if existing:
                if bool(existing[0][0]) == required:
                    return
                tx.execute("UPDATE task_dependencies SET required = ? WHERE task_id = ? AND depends_on_id = ?",
                           (int(required), task_id, depends_on_id))
            else:
                if rules.would_cycle(task_id, depends_on_id, edges):
                    raise TaskRuleError("dependência criaria ciclo (ou aponta para a própria tarefa)")
                tx.execute("INSERT INTO task_dependencies (task_id, depends_on_id, required) VALUES (?, ?, ?)",
                           (task_id, depends_on_id, int(required)))
            label = "required" if required else "optional"
            self._change(tx, task_id, "dependency", None, f"{depends_on_id}:{label}", actor, now)
            tx.audit(actor, "task.dependency", f"task:{task_id}", f"ok: depends_on={depends_on_id} {label}")
        self._run("task.dependency", actor, f"task:{task_id}", fn)
        return Dependency(task_id, depends_on_id, required)

    def get_task(self, task_id: str) -> Task | None:
        rows = self._repo.fetch(f"SELECT {_COLS} FROM tasks WHERE id = ?", (task_id,))
        return _task(rows[0]) if rows else None

    def list_tasks(self, status: str | None = None, assignee_kind: str | None = None,
                   assignee_id: str | None = None, stage_id: str | None = None,
                   parent_id: str | None = None) -> list[Task]:
        filters = {"status": status, "assignee_kind": assignee_kind, "assignee_id": assignee_id,
                   "stage_id": stage_id, "parent_task_id": parent_id}
        used = {k: v for k, v in filters.items() if v is not None}
        where = ("WHERE " + " AND ".join(f"{k} = ?" for k in used)) if used else ""
        rows = self._repo.fetch(f"SELECT {_COLS} FROM tasks {where} ORDER BY created_at, id", tuple(used.values()))
        return [_task(r) for r in rows]

    def dependencies(self, task_id: str) -> list[Dependency]:
        rows = self._repo.fetch(
            "SELECT task_id, depends_on_id, required FROM task_dependencies WHERE task_id = ? ORDER BY depends_on_id",
            (task_id,))
        return [Dependency(a, b, bool(r)) for a, b, r in rows]

    def subtasks(self, task_id: str) -> list[Task]:
        return self.list_tasks(parent_id=task_id)

    def is_ready(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        rows = self._repo.fetch(
            "SELECT t.id, t.status, d.required FROM task_dependencies d JOIN tasks t ON t.id = d.depends_on_id "
            "WHERE d.task_id = ?", (task_id,))
        return rules.is_ready(task.status, [(i, s, bool(r)) for i, s, r in rows])

    def changes(self, task_id: str) -> list[TaskChange]:
        rows = self._repo.fetch(
            "SELECT task_id, field, old_value, new_value, actor, at FROM task_changes WHERE task_id = ? ORDER BY id",
            (task_id,))
        return [TaskChange(*r) for r in rows]
