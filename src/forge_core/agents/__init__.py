from .echo import EchoAgent
from .orchestrator import DispatchResult, Orchestrator
from .provider import ProviderAdapter, ProviderResponse
from .registry import AgentRegistry
from .runtime import RunResult
from .spec import Agent, AgentContext, AgentOutcome, AgentSpec, Permission


def default_registry() -> AgentRegistry:
    """Registro padrão desta entrega: só o `echo` (read). Nenhum agente write/critical até existir autenticação."""
    registry = AgentRegistry()
    registry.register(EchoAgent())
    return registry


__all__ = ["Agent", "AgentContext", "AgentOutcome", "AgentRegistry", "AgentSpec", "DispatchResult",
           "EchoAgent", "Orchestrator", "Permission", "ProviderAdapter", "ProviderResponse", "RunResult",
           "default_registry"]
