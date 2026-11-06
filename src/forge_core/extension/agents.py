"""Contrato de agente (ADR-011). Reexporta o contrato definido em `forge_core.agents`."""
from ..agents.spec import Agent, AgentContext, AgentOutcome, AgentSpec

__all__ = ["Agent", "AgentContext", "AgentOutcome", "AgentSpec"]
