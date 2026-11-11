"""Semente idempotente dos repositórios permitidos da org ferreiraeborzone (ADR-017).

`default_branch` é o placeholder `main`: o Core não consulta o GitHub para conferir a branch real.
O projeto cadastro chama-se FORGE. A tela de tarefas usa `list_active_allowed_repos` (só a allowlist).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..projects.model import RepositoryInfo
from .sql import SqlRepository

ORG = "ferreiraeborzone"
PROJECT_TITLE = "FORGE"
DEFAULT_BRANCH = "main"
PROVIDER = "github"
ALLOWED_REPOS = (
    "sistema-cobranca-monolith",
    "sistema-feb-monolith",
    "sistema-gestao-monolith",
    "site",
    "ferreiraeborzone_docs",
)

_RCOLS = (
    "r.id, r.project_id, r.name, r.provider, r.owner, r.repo_name, r.default_branch, r.active, "
    "r.settings, r.version, r.created_at, r.updated_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_allowed_repos(repo: SqlRepository, now: str | None = None) -> str:
    """Garante o projeto FORGE e os 5 repositórios. Devolve o id do projeto. Idempotente."""
    ts = now or _now()
    with repo.transaction() as tx:
        rows = tx.execute("SELECT id FROM projects WHERE title = ?", (PROJECT_TITLE,)).fetchall()
        if rows:
            project_id = rows[0][0]
        else:
            project_id = str(uuid.uuid4())
            tx.execute(
                "INSERT INTO projects (id, title, description, active, version, created_at, updated_at) "
                "VALUES (?, ?, '', 1, 1, ?, ?)",
                (project_id, PROJECT_TITLE, ts, ts),
            )
        for name in ALLOWED_REPOS:
            found = tx.execute(
                "SELECT id FROM repositories WHERE provider = ? AND lower(owner) = lower(?) "
                "AND lower(repo_name) = lower(?)",
                (PROVIDER, ORG, name),
            ).fetchall()
            if found:
                continue
            rid = str(uuid.uuid4())
            tx.execute(
                "INSERT INTO repositories (id, project_id, name, provider, owner, repo_name, "
                "default_branch, active, settings, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, '{}', 1, ?, ?)",
                (rid, project_id, name, PROVIDER, ORG, name, DEFAULT_BRANCH, ts, ts),
            )
    return project_id


def list_active_allowed_repos(repo: SqlRepository) -> list[RepositoryInfo]:
    """Repositórios ativos da allowlist (github / ferreiraeborzone / ALLOWED_REPOS). Sem chamada ao GitHub."""
    placeholders = ",".join("?" for _ in ALLOWED_REPOS)
    rows = repo.fetch(
        f"SELECT {_RCOLS} FROM repositories r JOIN projects p ON p.id = r.project_id "
        "WHERE r.active = 1 AND p.active = 1 AND r.provider = ? AND lower(r.owner) = lower(?) "
        f"AND lower(r.repo_name) IN ({placeholders}) "
        "ORDER BY r.owner, r.repo_name, r.id",
        (PROVIDER, ORG, *[name.lower() for name in ALLOWED_REPOS]),
    )
    out = []
    for r in rows:
        settings = r[8]
        if isinstance(settings, str):
            settings = json.loads(settings)
        out.append(
            RepositoryInfo(
                r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7]),
                settings or {}, r[9], r[10], r[11],
            )
        )
    return out
