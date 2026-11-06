from __future__ import annotations

from ..errors import AgentError
from .approval import PRIVILEGED_DISABLED_MESSAGE
from .spec import Agent


class AgentRegistry:
    """Registro de agentes. Agente novo = `register(agent)`; o Orchestrator não muda.

    Fronteira de segurança (ADR-011): enquanto não existir autenticação de aprovadores, SÓ agentes
    exclusivamente `read` podem ser registrados. Não há flag nem construtor que mude isso.
    """

    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        spec = agent.spec
        if spec.name in self._agents:
            raise AgentError(f"agente já registrado: {spec.name}")
        if spec.requires_approval:
            raise AgentError(
                f"agente {spec.name}: permissões {list(spec.permissions)} recusadas; "
                f"{PRIVILEGED_DISABLED_MESSAGE}"
            )
        self._agents[spec.name] = agent

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def names(self) -> list[str]:
        return sorted(self._agents)
