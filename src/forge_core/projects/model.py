from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass(frozen=True)
class ProjectInfo:
    """Projeto gerenciável (FRG-5). `tasks.Project` continua sendo a visão enxuta usada pelas tarefas."""
    id: str
    title: str
    description: str
    active: bool
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RepositoryInfo:
    id: str
    project_id: str
    name: str
    provider: str
    owner: str
    repo_name: str
    default_branch: str
    active: bool
    settings: dict = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class RepositoryTarget(NamedTuple):
    """O que a FRG-21 precisa para criar issue e branch. `base_branch` já considera `base_branch_override`."""
    provider: str
    owner: str
    repo_name: str
    base_branch: str
    settings: dict
