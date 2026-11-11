"""Corridas de autorização (SQLite e Postgres). Determinísticas: barreiras e eventos, sem depender de tempo.

Regra testada: toda escrita confere sessão e papel DENTRO da seção serializada, e revogação confirmada antes
dessa seção impede o efeito. Uma escrita que confirma antes do lock da revogação permanece (linearização).
"""
import threading

import pytest

from auth_helpers import actor
from forge_core.agents.approval import ApprovalLedger
from forge_core.auth.store import AuthStore
from forge_core.errors import ApprovalError, AuthenticationError, AuthorizationError
from forge_core.projects import ProjectService
from forge_core.tasks import TaskService


def _role_grant_id(repo, identity_id, role):
    return repo.fetch("SELECT id FROM role_grants WHERE identity_id = ? AND role = ?", (identity_id, role))[0][0]


def _racer(fn):
    out = {}

    def run():
        try:
            out["value"] = fn()
        except Exception as exc:  # o teste confere o tipo e a mensagem
            out["error"] = exc

    th = threading.Thread(target=run, name="racer")
    th.start()
    return th, out


def _gate_before_section(monkeypatch, gate, release):
    """Pausa a thread `racer` logo depois da checagem de fora da seção (antes do lock)."""
    orig = AuthStore.require

    def wrapped(self, principal, role):
        result = orig(self, principal, role)
        if threading.current_thread().name == "racer" and not gate.is_set():
            gate.set()
            release.wait(30)
        return result

    monkeypatch.setattr(AuthStore, "require", wrapped)


def _gate_inside_section(monkeypatch, gate, release):
    """Pausa a thread `racer` DENTRO da seção serializada (lock já adquirido)."""
    orig = AuthStore.serialize_authorization

    def wrapped(self, tx):
        orig(self, tx)
        if threading.current_thread().name == "racer" and not gate.is_set():
            gate.set()
            release.wait(30)

    monkeypatch.setattr(AuthStore, "serialize_authorization", wrapped)


def _setup_people(make_repo):
    repo = make_repo()
    dona = actor(repo, "dona")
    ana = actor(repo, "ana")
    svc = TaskService(repo)
    task = svc.create_task("base", ana)
    return repo, dona, ana, svc, task


@pytest.mark.parametrize("op", ["create_task", "update_task", "create_project"])
def test_revocation_confirmed_before_section_blocks_the_write(make_repo, monkeypatch, op):
    repo, dona, ana, svc, task = _setup_people(make_repo)
    gate, release = threading.Event(), threading.Event()
    _gate_before_section(monkeypatch, gate, release)

    def write():
        racer_repo = make_repo()
        if op == "create_task":
            return TaskService(racer_repo).create_task("nova", ana)
        if op == "update_task":
            return TaskService(racer_repo).update_task(task.id, ana, 1, title="nova")
        return ProjectService(racer_repo).create_project("projeto novo", ana)

    th, out = _racer(write)
    assert gate.wait(30)
    AuthStore(repo).revoke_role(dona, _role_grant_id(repo, "gh:1001", "editor"))  # confirmada antes da seção
    release.set()
    th.join(30)
    assert not th.is_alive()
    assert isinstance(out.get("error"), AuthenticationError) and "invalid_session" in str(out["error"])
    assert repo.fetch("SELECT COUNT(*) FROM tasks")[0][0] == 1
    assert repo.fetch("SELECT COUNT(*) FROM projects")[0][0] == 0
    assert svc.get_task(task.id).title == "base" and svc.get_task(task.id).version == 1


def test_self_approval_race_is_rechecked_inside_the_section(make_repo, monkeypatch):
    """Quem edita e aprova: a edição confirma depois da checagem de fora da seção. A aprovação ainda é recusada."""
    repo, dona, ana, svc, _ = _setup_people(make_repo)
    AuthStore(repo).grant_role(dona, 1001, "approver")
    t = svc.create_task("tarefa do agente", ana, assignee_kind="agent", assignee_id="priv")
    gate, release = threading.Event(), threading.Event()
    _gate_before_section(monkeypatch, gate, release)

    th, out = _racer(lambda: ApprovalLedger(make_repo()).grant(t.id, ana, "priv"))
    assert gate.wait(30)
    svc.update_task(t.id, ana, 1, title="editada pela própria aprovadora")  # v2, confirmada antes do lock
    release.set()
    th.join(30)
    assert isinstance(out.get("error"), ApprovalError) and "self_approval" in str(out["error"])
    assert repo.fetch("SELECT COUNT(*) FROM approval_grants")[0][0] == 0
    assert ApprovalLedger(repo).available(t.id, "priv") == 0


def test_approval_refused_when_approver_role_revoked_before_section(make_repo, monkeypatch):
    repo, dona, ana, svc, _ = _setup_people(make_repo)
    chefe = actor(repo, "chefe")
    t = svc.create_task("tarefa", ana, assignee_kind="agent", assignee_id="priv")
    gate, release = threading.Event(), threading.Event()
    _gate_before_section(monkeypatch, gate, release)

    th, out = _racer(lambda: ApprovalLedger(make_repo()).grant(t.id, chefe, "priv"))
    assert gate.wait(30)
    AuthStore(repo).revoke_role(dona, _role_grant_id(repo, "gh:1003", "approver"))
    release.set()
    th.join(30)
    err = out.get("error")
    assert isinstance(err, ApprovalError) and "invalid_session" in str(err)
    assert repo.fetch("SELECT COUNT(*) FROM approval_grants")[0][0] == 0


def test_revocation_waits_for_a_write_inside_the_section_and_the_write_survives(make_repo, monkeypatch):
    """Escrita que já entrou na seção confirma; a revogação espera e só vale para operações depois dela."""
    repo, dona, ana, svc, _ = _setup_people(make_repo)
    gid = _role_grant_id(repo, "gh:1001", "editor")
    gate, release = threading.Event(), threading.Event()
    _gate_inside_section(monkeypatch, gate, release)

    th, out = _racer(lambda: TaskService(make_repo()).create_task("dentro da seção", ana))
    assert gate.wait(30)
    revoker_out = {}

    def revoke():
        try:
            AuthStore(make_repo()).revoke_role(dona, gid)
        except Exception as exc:
            revoker_out["error"] = exc

    rv = threading.Thread(target=revoke, name="revoker")
    rv.start()
    rv.join(0.5)
    assert rv.is_alive(), "a revogação não pode passar enquanto a escrita está na seção"
    release.set()
    th.join(30)
    rv.join(30)
    assert out.get("error") is None and out.get("value") is not None
    assert "error" not in revoker_out and not rv.is_alive()
    with pytest.raises(AuthenticationError, match="invalid_session"):
        svc.create_task("depois da revogação", ana)
    titles = [r[0] for r in repo.fetch("SELECT title FROM tasks ORDER BY title")]
    assert "dentro da seção" in titles and "depois da revogação" not in titles


def test_revoked_session_cannot_grant_or_revoke_roles(make_repo):
    repo, dona, ana, svc, _ = _setup_people(make_repo)
    AuthStore(repo).revoke_session(dona)  # confirmada antes de qualquer operação
    with pytest.raises(AuthenticationError, match="invalid_session"):
        AuthStore(repo).grant_role(dona, 1002, "editor")
    with pytest.raises(AuthenticationError, match="invalid_session"):
        AuthStore(repo).revoke_role(dona, _role_grant_id(repo, "gh:1001", "editor"))
    assert repo.fetch("SELECT COUNT(*) FROM role_grants WHERE identity_id = 'gh:1002'")[0][0] == 1  # só o elenco
    assert repo.fetch("SELECT COUNT(*) FROM role_revocations")[0][0] == 0


def test_revoke_session_is_itself_serialized_and_idempotent_in_effect(make_repo):
    repo, dona, ana, svc, _ = _setup_people(make_repo)
    AuthStore(repo).revoke_session(ana)
    with pytest.raises(AuthenticationError, match="invalid_session"):
        AuthStore(repo).revoke_session(ana)
    with pytest.raises(AuthenticationError, match="invalid_session"):
        svc.create_task("sessão revogada", ana)
