class ForgeError(Exception):
    """Erro base do Forge Core."""


class ConfigError(ForgeError):
    """Configuração ausente ou inválida na inicialização."""
