"""Pontos de extensão do Core. Só interfaces; implementações ficam fora do pacote `extension`."""
from .agents import Agent, AgentResult
from .integrations import Integration
from .queue import Job, JobQueue, JobStatus

__all__ = ["Agent", "AgentResult", "Integration", "Job", "JobQueue", "JobStatus"]
