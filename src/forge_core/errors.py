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


class TaskRuleError(ForgeError):
    """Violação de regra de tarefa: transição inválida, dependência pendente, ciclo, campo inválido."""


class TaskConflictError(ForgeError):
    """A tarefa mudou desde a leitura (version diferente): releia e tente de novo."""


class AgentError(ForgeError):
    """Ficha de agente inválida ou registro recusado."""


class AgentFailure(ForgeError):
    """Falha de agente com mensagem explícita e segura (vai para o registro após redact()).

    Qualquer outra exceção do agente é registrada só pelo tipo. Nunca ponha contexto da tarefa na mensagem.
    """


class DispatchRefusedError(ForgeError):
    """O orquestrador recusou despachar (tarefa não pronta, sem agente, sem aprovação...). É auditado."""


class ApprovalError(ForgeError):
    """Aprovação recusada (aprovador não é pessoa, tarefa inexistente)."""


class ProjectRuleError(ForgeError):
    """Violação de regra de projeto/repositório: dado inválido, duplicidade, inativo, inexistente."""


class ProjectConflictError(ForgeError):
    """O projeto ou repositório mudou desde a leitura (version diferente): releia e tente de novo."""
