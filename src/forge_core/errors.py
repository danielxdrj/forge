class ForgeError(Exception):
    """Erro base do Forge Core."""


class ConfigError(ForgeError):
    """Configuração ausente ou inválida na inicialização."""


class AutomationDisabledError(ForgeError):
    """Automação bloqueada pela chave global FORGE_AUTOMATION_ENABLED."""
