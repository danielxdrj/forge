"""Contrato de agente (ADR-011). Stdlib apenas; nenhuma IA aqui.

Para criar um agente: defina um `AgentSpec` (a ficha) e uma classe com `spec` e `run(ctx)`.
Veja `agents/README.md` para a ficha completa e um exemplo.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..errors import AgentError
from ..logging import redact
from ..tasks.model import Task

_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")


class Permission:
    READ = "read"
    WRITE = "write"
    CRITICAL = "critical"
    KNOWN = (READ, WRITE, CRITICAL)


@dataclass(frozen=True)
class AgentSpec:
    """Ficha do agente. O que não for exatamente `read` exige aprovação humana antes do despacho."""

    name: str
    responsibility: str
    scope: str
    tools: tuple[str, ...]
    permissions: tuple[str, ...]
    execution: str
    version: str = "0.1.0"
    timeout_seconds: float = 60.0
    active: bool = True

    def __post_init__(self):
        if not _NAME.match(self.name):
            raise AgentError("nome do agente: minúsculas, números, - ou _ (2 a 40 caracteres)")
        for field_name in ("responsibility", "scope", "execution", "version"):
            if not str(getattr(self, field_name)).strip():
                raise AgentError(f"ficha do agente: {field_name} é obrigatório")
        if self.timeout_seconds <= 0:
            raise AgentError("timeout_seconds deve ser positivo")

    @property
    def requires_approval(self) -> bool:
        """Somente `read` despacha direto. Permissão desconhecida, ou nenhuma, exige aprovação (ADR-006)."""
        return not (self.permissions and all(p == Permission.READ for p in self.permissions))


@dataclass
class AgentContext:
    """Entrada de uma execução. O agente deve checar `cancel_event` em trabalhos longos."""

    task: Task
    actor: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Registro de atividades do agente. Passa por redact() antes de ficar guardado."""
        self._logs.append(redact(str(message)))

    @property
    def logs(self) -> list[str]:
        return list(self._logs)


@dataclass(frozen=True)
class AgentOutcome:
    """Resultado estruturado. `status` é `success` ou `failure`; `usage` e `cost` são opcionais."""

    status: str = "success"
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    cost: float | None = None


class Agent(Protocol):
    spec: AgentSpec

    def run(self, ctx: AgentContext) -> AgentOutcome: ...
