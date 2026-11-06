from __future__ import annotations

from ..errors import AgentError
from .spec import Agent


class AgentRegistry:
    """Registro de agentes. Agente novo = `register(agent)`; o Orchestrator não muda.

    Regra de segurança (ADR-011): enquanto não existir autenticação de aprovadores, só agentes
    exclusivamente `read` podem ser registrados. `allow_privileged=True` existe SÓ para testes.
    """

    def __init__(self, allow_privileged: bool = False):
        self._agents: dict[str, Agent] = {}
        self._allow_privileged = allow_privileged

    def register(self, agent: Agent) -> None:
        spec = agent.spec
        if spec.name in self._agents:
            raise AgentError(f"agente já registrado: {spec.name}")
        if spec.requires_approval and not self._allow_privileged:
            raise AgentError(
                f"agente {spec.name}: permissões {list(spec.permissions)} exigem aprovação autenticada, "
                "que ainda não existe; só agentes read podem ser registrados"
            )
        self._agents[spec.name] = agent

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def names(self) -> list[str]:
        return sorted(self._agents)
