"""Gerenciamento de projetos e repositórios sobre SqlRepository (ADR-012).

Cada mudança grava, na mesma transação, a alteração e a auditoria. A auditoria registra só ids e nomes de
campos, nunca valores livres (descrição, settings). Recusas também são auditadas. Nada é apagado: desativar
é `active = 0`. Sem chamadas externas: o serviço não verifica se o repositório existe no GitHub (FRG-21).
O ator é o informado, sem autenticação (limitação aceita pelo gestor de projetos).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from ..errors import ProjectConflictError, ProjectRuleError
from ..storage.sql import SqlRepository
from . import rules
from .model import ProjectInfo, RepositoryInfo, RepositoryTarget

_PCOLS = "id, title, description, active, version, created_at, COALESCE(updated_at, created_at)"
_RCOLS = ("id, project_id, name, provider, owner, repo_name, default_branch, active, settings, version, "
          "created_at, updated_at")
_REFUSALS = (ProjectRuleError, ProjectConflictError)
_UNIQUE = ("IntegrityError", "UniqueViolation")


def _project(r) -> ProjectInfo:
    return ProjectInfo(r[0], r[1], r[2], bool(r[3]), r[4], r[5], r[6])


def _repo(r) -> RepositoryInfo:
    return RepositoryInfo(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7]), json.loads(r[8]), r[9], r[10], r[11])


class ProjectService:
    def __init__(self, repo: SqlRepository, clock: Callable[[], datetime] | None = None):
        self._repo = repo
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        return self._clock().isoformat()

    def _lock(self) -> str:
        return " FOR UPDATE" if self._repo.dialect == "postgres" else ""

    def _run(self, action: str, actor: str, target: str, fn):
        err: Exception | None = None
        result = None
        with self._repo.transaction() as tx:
            try:
                result = fn(tx, self._now())
            except _REFUSALS as exc:
                err = exc
            except Exception as exc:
                if type(exc).__name__ not in _UNIQUE:
                    raise
                err = ProjectRuleError("repositório já cadastrado (provider, owner, repo_name)")
        if err is not None:
            self._repo.record_audit(actor, action, target, f"error: {err}")
            raise err
        return result

    # --- leitura ---

    def _load_project(self, tx, project_id: str, lock: str = "") -> ProjectInfo:
        rows = tx.execute(f"SELECT {_PCOLS} FROM projects WHERE id = ?{lock}", (project_id,)).fetchall()
        if not rows:
            raise ProjectRuleError(f"projeto inexistente: {project_id}")
        return _project(rows[0])

    def _load_repo(self, tx, repository_id: str, lock: str = "") -> RepositoryInfo:
        rows = tx.execute(f"SELECT {_RCOLS} FROM repositories WHERE id = ?{lock}", (repository_id,)).fetchall()
        if not rows:
            raise ProjectRuleError(f"repositório inexistente: {repository_id}")
        return _repo(rows[0])

    def get_project(self, project_id: str) -> ProjectInfo | None:
        rows = self._repo.fetch(f"SELECT {_PCOLS} FROM projects WHERE id = ?", (project_id,))
        return _project(rows[0]) if rows else None

    def list_projects(self, active_only: bool = False) -> list[ProjectInfo]:
        where = " WHERE active = 1" if active_only else ""
        return [_project(r) for r in self._repo.fetch(f"SELECT {_PCOLS} FROM projects{where} ORDER BY created_at, id")]

    def get_repository(self, repository_id: str) -> RepositoryInfo | None:
        rows = self._repo.fetch(f"SELECT {_RCOLS} FROM repositories WHERE id = ?", (repository_id,))
        return _repo(rows[0]) if rows else None

    def list_repositories(self, project_id: str | None = None, active_only: bool = False) -> list[RepositoryInfo]:
        conds, params = [], []
        if project_id is not None:
            conds.append("project_id = ?")
            params.append(project_id)
        if active_only:
            conds.append("active = 1")
        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        rows = self._repo.fetch(f"SELECT {_RCOLS} FROM repositories{where} ORDER BY created_at, id", tuple(params))
        return [_repo(r) for r in rows]

    def resolve_target(self, repository_id: str) -> RepositoryTarget:
        """Leitura para a FRG-21: (provider, owner, repo_name, base_branch, settings). Recusa inativo ou inexistente."""
        rows = self._repo.fetch(
            "SELECT r.provider, r.owner, r.repo_name, r.default_branch, r.settings, r.active, p.active "
            "FROM repositories r JOIN projects p ON p.id = r.project_id WHERE r.id = ?", (repository_id,))
        if not rows:
            raise ProjectRuleError(f"repositório inexistente: {repository_id}")
        provider, owner, repo_name, default_branch, settings, r_active, p_active = rows[0]
        if not p_active:
            raise ProjectRuleError("projeto inativo")
        if not r_active:
            raise ProjectRuleError("repositório inativo")
        settings = json.loads(settings)
        return RepositoryTarget(provider, owner, repo_name, settings.get("base_branch_override") or default_branch,
                                settings)

    # --- projetos ---

    def create_project(self, title: str, actor: str, description: str = "") -> ProjectInfo:
        def fn(tx, now):
            t, d = rules.validate_title(title), rules.validate_description(description)
            pid = str(uuid.uuid4())
            tx.execute("INSERT INTO projects (id, title, description, active, version, created_at, updated_at) "
                       "VALUES (?, ?, ?, 1, 1, ?, ?)", (pid, t, d, now, now))
            tx.audit(actor, "project.create", f"project:{pid}", "ok")
            return ProjectInfo(pid, t, d, True, 1, now, now)
        return self._run("project.create", actor, "project:new", fn)

    def update_project(self, project_id: str, actor: str, expected_version: int, *, title: str | None = None,
                       description: str | None = None) -> ProjectInfo:
        def fn(tx, now):
            cur = self._load_project(tx, project_id, self._lock())
            if cur.version != expected_version:
                raise ProjectConflictError(f"version esperada {expected_version}, atual {cur.version}")
            new_t = rules.validate_title(title) if title is not None else cur.title
            new_d = rules.validate_description(description) if description is not None else cur.description
            changed = [f for f, a, b in (("title", cur.title, new_t), ("description", cur.description, new_d)) if a != b]
            if not changed:
                return cur
            tx.execute("UPDATE projects SET title = ?, description = ?, version = version + 1, updated_at = ? "
                       "WHERE id = ? AND version = ?", (new_t, new_d, now, project_id, expected_version))
            tx.audit(actor, "project.update", f"project:{project_id}", f"ok: fields={','.join(changed)}")
            return ProjectInfo(cur.id, new_t, new_d, cur.active, cur.version + 1, cur.created_at, now)
        return self._run("project.update", actor, f"project:{project_id}", fn)

    def deactivate_project(self, project_id: str, actor: str, expected_version: int | None = None) -> ProjectInfo:
        """Desativa o projeto e, em cascata, todos os repositórios dele (na mesma transação)."""
        def fn(tx, now):
            cur = self._load_project(tx, project_id, self._lock())
            if expected_version is not None and cur.version != expected_version:
                raise ProjectConflictError(f"version esperada {expected_version}, atual {cur.version}")
            if not cur.active:
                return cur
            tx.execute("UPDATE projects SET active = 0, version = version + 1, updated_at = ? WHERE id = ?",
                       (now, project_id))
            ids = [r[0] for r in tx.execute("SELECT id FROM repositories WHERE project_id = ? AND active = 1 "
                                            "ORDER BY id", (project_id,)).fetchall()]
            tx.execute("UPDATE repositories SET active = 0, version = version + 1, updated_at = ? "
                       "WHERE project_id = ? AND active = 1", (now, project_id))
            tx.audit(actor, "project.deactivate", f"project:{project_id}", f"ok: repositories={len(ids)}")
            for rid in ids:
                tx.audit(actor, "repository.deactivate", f"repository:{rid}", "ok: cascade")
            return ProjectInfo(cur.id, cur.title, cur.description, False, cur.version + 1, cur.created_at, now)
        return self._run("project.deactivate", actor, f"project:{project_id}", fn)

    def reactivate_project(self, project_id: str, actor: str, expected_version: int | None = None) -> ProjectInfo:
        """Reativa só o projeto. Os repositórios continuam inativos até serem reativados um a um."""
        def fn(tx, now):
            cur = self._load_project(tx, project_id, self._lock())
            if expected_version is not None and cur.version != expected_version:
                raise ProjectConflictError(f"version esperada {expected_version}, atual {cur.version}")
            if cur.active:
                return cur
            tx.execute("UPDATE projects SET active = 1, version = version + 1, updated_at = ? WHERE id = ?",
                       (now, project_id))
            tx.audit(actor, "project.reactivate", f"project:{project_id}", "ok")
            return ProjectInfo(cur.id, cur.title, cur.description, True, cur.version + 1, cur.created_at, now)
        return self._run("project.reactivate", actor, f"project:{project_id}", fn)

    # --- repositórios ---

    def add_repository(self, project_id: str, name: str, owner: str, repo_name: str, actor: str, *,
                       default_branch: str = "main", settings: dict | None = None,
                       provider: str = "github") -> RepositoryInfo:
        def fn(tx, now):
            n, o, rn = rules.validate_name(name), rules.validate_owner(owner), rules.validate_repo_name(repo_name)
            prov, branch = rules.validate_provider(provider), rules.validate_branch(default_branch, "default_branch")
            st = rules.validate_settings(settings or {})
            if not self._load_project(tx, project_id, self._lock()).active:
                raise ProjectRuleError("projeto inativo: não aceita novos repositórios")
            rid = str(uuid.uuid4())
            tx.execute(
                "INSERT INTO repositories (id, project_id, name, provider, owner, repo_name, default_branch, active, "
                "settings, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?)",
                (rid, project_id, n, prov, o, rn, branch, json.dumps(st, sort_keys=True), now, now))
            tx.audit(actor, "repository.create", f"repository:{rid}", "ok")
            return RepositoryInfo(rid, project_id, n, prov, o, rn, branch, True, st, 1, now, now)
        return self._run("repository.create", actor, f"project:{project_id}", fn)

    def update_repository(self, repository_id: str, actor: str, expected_version: int, *, name: str | None = None,
                          owner: str | None = None, repo_name: str | None = None, default_branch: str | None = None,
                          settings: dict | None = None) -> RepositoryInfo:
        """Edita campos. `settings`, quando informado, SUBSTITUI o objeto inteiro."""
        def fn(tx, now):
            cur = self._load_repo(tx, repository_id, self._lock())
            if cur.version != expected_version:
                raise ProjectConflictError(f"version esperada {expected_version}, atual {cur.version}")
            new = {
                "name": rules.validate_name(name) if name is not None else cur.name,
                "owner": rules.validate_owner(owner) if owner is not None else cur.owner,
                "repo_name": rules.validate_repo_name(repo_name) if repo_name is not None else cur.repo_name,
                "default_branch": (rules.validate_branch(default_branch, "default_branch")
                                   if default_branch is not None else cur.default_branch),
                "settings": rules.validate_settings(settings) if settings is not None else cur.settings,
            }
            changed = [f for f, v in new.items() if v != getattr(cur, f)]
            if not changed:
                return cur
            tx.execute(
                "UPDATE repositories SET name = ?, owner = ?, repo_name = ?, default_branch = ?, settings = ?, "
                "version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                (new["name"], new["owner"], new["repo_name"], new["default_branch"],
                 json.dumps(new["settings"], sort_keys=True), now, repository_id, expected_version))
            tx.audit(actor, "repository.update", f"repository:{repository_id}", f"ok: fields={','.join(changed)}")
            return RepositoryInfo(cur.id, cur.project_id, new["name"], cur.provider, new["owner"], new["repo_name"],
                                  new["default_branch"], cur.active, new["settings"], cur.version + 1,
                                  cur.created_at, now)
        return self._run("repository.update", actor, f"repository:{repository_id}", fn)

    def _set_repo_active(self, repository_id: str, actor: str, expected_version: int | None, active: bool):
        action = "repository.reactivate" if active else "repository.deactivate"

        def fn(tx, now):
            cur = self._load_repo(tx, repository_id, self._lock())
            if expected_version is not None and cur.version != expected_version:
                raise ProjectConflictError(f"version esperada {expected_version}, atual {cur.version}")
            if cur.active == active:
                return cur
            if active and not self._load_project(tx, cur.project_id, self._lock()).active:
                raise ProjectRuleError("projeto inativo: reative o projeto antes do repositório")
            tx.execute("UPDATE repositories SET active = ?, version = version + 1, updated_at = ? WHERE id = ?",
                       (1 if active else 0, now, repository_id))
            tx.audit(actor, action, f"repository:{repository_id}", "ok")
            return RepositoryInfo(cur.id, cur.project_id, cur.name, cur.provider, cur.owner, cur.repo_name,
                                  cur.default_branch, active, cur.settings, cur.version + 1, cur.created_at, now)
        return self._run(action, actor, f"repository:{repository_id}", fn)

    def deactivate_repository(self, repository_id: str, actor: str, expected_version: int | None = None):
        return self._set_repo_active(repository_id, actor, expected_version, False)

    def reactivate_repository(self, repository_id: str, actor: str, expected_version: int | None = None):
        return self._set_repo_active(repository_id, actor, expected_version, True)
