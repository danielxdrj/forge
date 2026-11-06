class ForgeError(Exception):
    """Erro base do Forge Core."""


class ConfigError(ForgeError):
    """Configuração ausente ou inválida na inicialização."""


class AutomationDisabledError(ForgeError):
    """Automação bloqueada pela chave global FORGE_AUTOMATION_ENABLED."""


class JobStateError(ForgeError):
    """Operação inválida para o estado atual do job (ex.: completar job que não está running)."""
