"""Pontos de extensão do Core. Só interfaces; implementações ficam fora (ex.: fila na FRG-40)."""
from .agents import Agent, AgentResult
from .integrations import Integration
from .queue import TaskQueue

__all__ = ["Agent", "AgentResult", "Integration", "TaskQueue"]
