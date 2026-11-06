"""Pontos de extensão do Core. Só interfaces; implementações ficam fora do pacote `extension`."""
from .agents import Agent, AgentContext, AgentOutcome, AgentSpec
from .integrations import Integration
from .queue import Job, JobQueue, JobStatus

__all__ = ["Agent", "AgentContext", "AgentOutcome", "AgentSpec", "Integration", "Job", "JobQueue", "JobStatus"]
