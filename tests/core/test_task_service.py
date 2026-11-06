import threading
from datetime import datetime, timedelta, timezone

import pytest

from forge_core.errors import TaskConflictError, TaskRuleError
from forge_core.storage import SqlRepository, open_repository
from forge_core.storage.migrate import migrate
from forge_core.tasks import TaskService, TaskStatus as S

T0 = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


@pytest.fixture(params=["sqlite", "postgres"])
def make_service(request, tmp_path):
    """Fábrica (serviço, repo, relógio) para SQLite e, se disponível, Postgres (papel escritor)."""
    clock = Clock()
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 't.db'}"
        return lambda: (lambda r: (TaskService(r, clock), r, clock))(open_repository(url))
    writer, _, new_writer = request.getfixturevalue("pg_env")
    return lambda: (lambda r: (TaskService(r, clock), r, clock))(new_writer())


def walk(svc, task_id, *statuses):
    for st in statuses:
        svc.change_status(task_id, st, "pessoa:ana")


def test_create_and_read_full_model(make_service):
    svc, repo, _ = make_service()
    p = svc.create_project("Projeto", "pessoa:ana")
    st = svc.create_stage(p.id, "Etapa 1", "pessoa:ana")
    t = svc.create_task("Implementar", "pessoa:ana", objective="o", context="c", scope="s",
                        acceptance_criteria="a", priority="high", assignee_kind="agent", assignee_id="dev",
                        due_date="2026-04-01", stage_id=st.id)
    got = svc.get_task(t.id)
    assert (got.status, got.priority, got.assignee_kind, got.assignee_id, got.stage_id, got.version) == (
        "pending", "high", "agent", "dev", st.id, 1)
    assert [x.title for x in svc.list_projects()] == ["Projeto"] and svc.list_stages(p.id)[0].id == st.id
    assert svc.list_tasks(assignee_kind="agent", assignee_id="dev")[0].id == t.id
    assert svc.list_tasks(status="done") == []


def test_dependency_gates_execution_and_dates_are_set(make_service):
    svc, repo, _ = make_service()
    a, b = svc.create_task("a", "p"), svc.create_task("b", "p")
    svc.add_dependency(b.id, a.id, "p")
    assert not svc.is_ready(b.id) and svc.is_ready(a.id)
    with pytest.raises(TaskRuleError, match="dependências obrigatórias"):
        svc.change_status(b.id, S.IN_PROGRESS, "p")
    assert repo.list_audit()[-1].result.startswith("error")
    walk(svc, a.id, S.IN_PROGRESS, S.IN_VALIDATION, S.DONE)
    done = svc.get_task(a.id)
    assert done.start_date == "2026-03-01" and done.completed_at is not None
    assert svc.is_ready(b.id)
    svc.change_status(b.id, S.IN_PROGRESS, "p")


def test_optional_dependency_does_not_block(make_service):
    svc, *_ = make_service()
    a, b = svc.create_task("a", "p"), svc.create_task("b", "p")
    svc.add_dependency(b.id, a.id, "p", required=False)
    assert svc.is_ready(b.id)


def test_subtasks_block_parent_completion(make_service):
    svc, *_ = make_service()
    parent = svc.create_task("pai", "p")
    req = svc.create_task("obrigatória", "p", parent_id=parent.id)
    opt = svc.create_task("opcional", "p", parent_id=parent.id, required=False)
    walk(svc, parent.id, S.IN_PROGRESS, S.IN_VALIDATION)
    with pytest.raises(TaskRuleError, match="subtarefas obrigatórias"):
        svc.change_status(parent.id, S.DONE, "p")
    walk(svc, req.id, S.IN_PROGRESS, S.IN_VALIDATION, S.DONE)
    svc.change_status(parent.id, S.DONE, "p")  # a opcional pendente não bloqueia
    assert svc.get_task(opt.id).status == "pending"
    assert {s.id for s in svc.subtasks(parent.id)} == {req.id, opt.id}


def test_subtask_rules(make_service):
    svc, *_ = make_service()
    p = svc.create_project("P", "p")
    st = svc.create_stage(p.id, "E", "p")
    parent = svc.create_task("pai", "p", stage_id=st.id)
    sub = svc.create_task("sub", "p", parent_id=parent.id)
    assert sub.stage_id == st.id  # herda a etapa
    with pytest.raises(TaskRuleError, match="profundidade"):
        svc.create_task("neta", "p", parent_id=sub.id)
    with pytest.raises(KeyError):
        svc.create_task("x", "p", parent_id="nao-existe")
    with pytest.raises(KeyError):
        svc.create_task("x", "p", stage_id="nao-existe")


def test_cycle_and_self_dependency_refused(make_service):
    svc, repo, _ = make_service()
    a, b = svc.create_task("a", "p"), svc.create_task("b", "p")
    svc.add_dependency(b.id, a.id, "p")
    with pytest.raises(TaskRuleError, match="ciclo"):
        svc.add_dependency(a.id, b.id, "p")
    with pytest.raises(TaskRuleError):
        svc.add_dependency(a.id, a.id, "p")
    svc.add_dependency(b.id, a.id, "p")  # repetir é idempotente
    assert len(svc.dependencies(b.id)) == 1


def test_invalid_transition_refused_and_audited(make_service):
    svc, repo, _ = make_service()
    t = svc.create_task("a", "p")
    with pytest.raises(TaskRuleError, match="transição inválida"):
        svc.change_status(t.id, S.DONE, "p")
    assert svc.get_task(t.id).status == "pending" and svc.get_task(t.id).version == 1
    last = repo.list_audit()[-1]
    assert last.action == "task.status" and last.result.startswith("error")
    with pytest.raises(KeyError):
        svc.change_status("nao-existe", S.PENDING, "p")


def test_history_records_old_and_new_values(make_service):
    svc, repo, _ = make_service()
    t = svc.create_task("a", "p", priority="low")
    svc.update_task(t.id, "pessoa:ana", 1, priority="urgent", title="novo")
    svc.change_status(t.id, S.IN_PROGRESS, "agente:dev")
    ch = [(c.field, c.old_value, c.new_value, c.actor) for c in svc.changes(t.id)]
    assert ("status", None, "pending", "p") in ch
    assert ("priority", "low", "urgent", "pessoa:ana") in ch and ("title", "a", "novo", "pessoa:ana") in ch
    assert ("status", "pending", "in_progress", "agente:dev") in ch
    assert ("start_date", None, "2026-03-01", "agente:dev") in ch
    assert [e.status for e in repo.task_history(t.id)] == ["pending", "in_progress"]
    actions = [a.action for a in repo.list_audit() if a.action != "seed"]
    assert actions == ["task.create", "task.update", "task.status"]


def test_audit_never_contains_task_text(make_service):
    svc, repo, _ = make_service()
    t = svc.create_task("TITULOSENTINEL", "p", objective="OBJSENTINEL")
    svc.update_task(t.id, "p", 1, context="CTXSENTINEL")
    dump = repr(repo.list_audit())
    assert not any(x in dump for x in ("TITULOSENTINEL", "OBJSENTINEL", "CTXSENTINEL"))
    assert "fields=context" in dump


def test_optimistic_version_conflict(make_service):
    svc, repo, _ = make_service()
    svc2, _, _ = make_service()
    t = svc.create_task("a", "p")
    svc.update_task(t.id, "ana", 1, priority="high")
    with pytest.raises(TaskConflictError):
        svc2.update_task(t.id, "bia", 1, priority="low")  # leu a versão 1, já é 2
    with pytest.raises(TaskConflictError):
        svc2.change_status(t.id, S.IN_PROGRESS, "bia", expected_version=1)
    assert svc.get_task(t.id).priority == "high" and svc.get_task(t.id).version == 2
    svc2.update_task(t.id, "bia", 2, priority="low")


def test_update_noop_unknown_field_and_terminal(make_service):
    svc, *_ = make_service()
    t = svc.create_task("a", "p")
    assert svc.update_task(t.id, "p", 1, title="a").version == 1  # sem mudança, sem nova versão
    with pytest.raises(TaskRuleError, match="não editáveis"):
        svc.update_task(t.id, "p", 1, status="done")
    svc.change_status(t.id, S.CANCELLED, "p")
    with pytest.raises(TaskRuleError, match="cancelled"):
        svc.update_task(t.id, "p", 2, title="b")
    with pytest.raises(TaskRuleError):
        svc.change_status(t.id, S.PENDING, "p")


def test_planned_initial_status_and_assignee_pair(make_service):
    svc, *_ = make_service()
    t = svc.create_task("a", "p", status=S.PLANNED)
    assert t.status == "planned"
    with pytest.raises(TaskRuleError):
        svc.create_task("b", "p", status=S.DONE)
    with pytest.raises(TaskRuleError):
        svc.create_task("b", "p", assignee_kind="person")
    p = svc.update_task(t.id, "p", 1, assignee_kind="person", assignee_id="ana")
    assert (p.assignee_kind, p.assignee_id) == ("person", "ana")


def test_legacy_repository_api_stays_compatible(make_service):
    svc, repo, _ = make_service()
    legacy = repo.create_task("antiga", "pessoa:ana")
    repo.set_task_status(legacy.id, "running", "pessoa:ana")
    got = svc.get_task(legacy.id)
    assert got.status == "in_progress" and got.version == 2
    assert [c.new_value for c in svc.changes(legacy.id)] == ["pending", "in_progress"]


def test_task_log_tables_are_append_only_sqlite(tmp_path):
    import sqlite3

    repo = open_repository(f"sqlite:///{tmp_path / 'a.db'}")
    t = TaskService(repo).create_task("a", "p")
    for table in ("task_history", "task_changes"):
        for sql in (f"UPDATE {table} SET actor = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                repo._conn.execute(sql)
    assert len(TaskService(repo).changes(t.id)) == 1


@pytest.mark.parametrize("sql", ["UPDATE {t} SET actor = 'x'", "DELETE FROM {t}", "TRUNCATE {t}"])
@pytest.mark.parametrize("table", ["task_history", "task_changes"])
def test_task_log_tables_are_append_only_postgres(pg_env, table, sql):
    import psycopg

    writer, owner, _ = pg_env
    TaskService(writer).create_task("a", "p")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner._run([(sql.format(t=table), ())])  # o dono também é bloqueado pelo trigger
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql.format(t=table), ())])  # o escritor nem tem o privilégio


def test_postgres_writer_cannot_delete_new_tables(pg_env):
    import psycopg

    writer, _, _ = pg_env
    for table in ("projects", "stages", "task_dependencies", "tasks"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            writer._run([(f"DELETE FROM {table}", ())])


# --- Migração 0005 com dados existentes (status antigos created/running/done) ---

SEED = [("t1", "created"), ("t2", "running"), ("t3", "done")]


def _seed_and_migrate(conn, dialect):
    ph = "?" if dialect == "sqlite" else "%s"
    assert migrate(conn, dialect, ph, up_to="0004")[-1].startswith("0004")
    cur = conn.cursor()
    for tid, st in SEED:
        cur.execute(f"INSERT INTO tasks (id, title, status, created_at, updated_at) VALUES ({ph},{ph},{ph},{ph},{ph})",
                    (tid, f"tarefa {tid}", st, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
        for i, hist in enumerate(["created"] + (["running"] if st != "created" else []) + (["done"] if st == "done" else [])):
            cur.execute(f"INSERT INTO task_history (task_id, status, actor, at) VALUES ({ph},{ph},{ph},{ph})",
                        (tid, hist, "pessoa:ana", f"2026-01-0{i + 1}T00:00:00+00:00"))
    cur.execute(f"INSERT INTO audit_log (at, actor, action, target, result) VALUES ({ph},{ph},{ph},{ph},{ph})",
                ("2026-01-01T00:00:00+00:00", "pessoa:ana", "task.create", "task:t1", "ok"))
    conn.commit()
    before = [tuple(r) for r in _all(conn, "SELECT id, task_id, actor, at FROM task_history ORDER BY id")]
    repo = SqlRepository(conn, dialect)  # aplica 0005
    return repo, before


def _all(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    conn.commit()
    return rows


def _check_migrated(repo, before):
    svc = TaskService(repo)
    assert {t.id: t.status for t in svc.list_tasks()} == {"t1": "pending", "t2": "in_progress", "t3": "done"}
    t1 = svc.get_task("t1")
    assert (t1.version, t1.priority, t1.objective, t1.assignee_kind, t1.parent_task_id) == (1, "normal", "", None, None)
    hist = {tid: [e.status for e in repo.task_history(tid)] for tid, _ in SEED}
    assert hist == {"t1": ["pending"], "t2": ["pending", "in_progress"], "t3": ["pending", "in_progress", "done"]}
    after = [tuple(r) for r in _all(repo._conn, "SELECT id, task_id, actor, at FROM task_history ORDER BY id")]
    assert after == before  # mesmas linhas, ids, atores e datas; só o vocabulário do status mudou
    assert len(repo.list_audit()) == 1 and repo.list_audit()[0].action == "task.create"
    # dados migrados já funcionam com as regras novas
    svc.change_status("t1", S.IN_PROGRESS, "pessoa:ana")
    assert svc.get_task("t1").status == "in_progress"
    assert svc.get_task("t3").status == "done"


def test_migration_0005_remaps_existing_data_sqlite(tmp_path):
    import sqlite3

    conn = sqlite3.connect(tmp_path / "m.db")
    _check_migrated(*_seed_and_migrate(conn, "sqlite"))


def test_migration_0005_remaps_existing_data_postgres(pg_blank):
    _check_migrated(*_seed_and_migrate(pg_blank, "postgres"))


# --- Corrida em add_dependency: validar ciclo e inserir precisa ser atômico ---

def _race_add_dependency(make_service, setup_edges, racing):
    """Duas conexões independentes, com barreira logo após a leitura das arestas.

    Com a serialização (advisory lock no Postgres, BEGIN IMMEDIATE no SQLite) a segunda chamada só lê as
    arestas depois que a primeira confirmou; a barreira então expira (timeout) e a execução segue.
    Sem serialização as duas chegam à barreira juntas e as duas validam sobre o mesmo grafo antigo.
    """
    setup, _, _ = make_service()
    ids = {name: setup.create_task(name, "p").id for name in "ABC"}
    for a, b in setup_edges:
        setup.add_dependency(ids[a], ids[b], "p")
    barrier = threading.Barrier(2)

    def hook():
        try:
            barrier.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass

    results = {}

    def run(i, a, b):
        svc, _, _ = make_service()
        svc._after_edges_read = hook
        try:
            svc.add_dependency(ids[a], ids[b], "p")
            results[i] = "ok"
        except Exception as exc:
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i, a, b)) for i, (a, b) in enumerate(racing)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)

    outcomes = list(results.values())
    assert outcomes.count("ok") == 1, outcomes
    failure = next(o for o in outcomes if o != "ok")
    assert isinstance(failure, TaskRuleError) and "ciclo" in str(failure)

    edges = {}
    for a in ids.values():
        for d in setup.dependencies(a):
            edges.setdefault(d.task_id, set()).add(d.depends_on_id)
    for task, deps in edges.items():
        for dep in deps:
            from forge_core.tasks.rules import would_cycle

            without = {k: v - {dep} if k == task else v for k, v in edges.items()}
            assert not would_cycle(task, dep, without), f"ciclo no banco: {task} -> {dep}"


def test_concurrent_two_node_cycle_exactly_one_wins(make_service):
    _race_add_dependency(make_service, [], [("A", "B"), ("B", "A")])


def test_concurrent_three_node_cycle_exactly_one_wins(make_service):
    _race_add_dependency(make_service, [("A", "B")], [("B", "C"), ("C", "A")])
