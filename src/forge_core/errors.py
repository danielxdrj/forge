class ForgeError(Exception):
    """Erro base do Forge Core."""


class ConfigError(ForgeError):
    """Configuração ausente ou inválida na inicialização."""


class AutomationDisabledError(ForgeError):
    """Automação bloqueada pela chave global FORGE_AUTOMATION_ENABLED."""


class JobStateError(ForgeError):
    """Operação inválida para o estado atual do job (ex.: completar job que não está running)."""


class JobFailure(ForgeError):
    """Falha de handler com mensagem explícita e segura (vai para last_error e auditoria, após redact()).

    Qualquer outra exceção do handler é registrada só pelo tipo. Nunca ponha payload na mensagem.
    `retryable=False` leva o job direto à falha definitiva.
    """

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable
