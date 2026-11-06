"""Agente de teste `echo`: sem IA, só repete a tarefa. Valida o fluxo do Forge.

FICHA DO AGENTE
- Responsabilidade: devolver título e objetivo da tarefa, para provar despacho, resultado e histórico.
- Escopo: nada além de repetir texto recebido. Não lê nem escreve em sistema algum.
- Ferramentas autorizadas: nenhuma.
- Permissões: somente `read`.
- Forma de execução: em processo, numa thread do Agent Runtime, timeout de 5 s.
- Comunicação com o Forge: recebe `AgentContext` (tarefa, ator, cancel_event); devolve `AgentOutcome`.
- Registro de atividades: uma linha de log por execução; `usage` conta caracteres; `cost` é 0.
- Critérios de validação: `tests/core/test_orchestrator.py` (despacho de tarefa pronta e recusa de não pronta).
- Manutenção: sem dependências; não deve ganhar ferramentas nem permissões (é o agente de referência).
"""
from __future__ import annotations

from ..tasks.model import Task
from .spec import AgentContext, AgentOutcome, AgentSpec, Permission


class EchoAgent:
    spec = AgentSpec(
        name="echo",
        responsibility="Repetir título e objetivo da tarefa (agente de teste, sem IA)",
        scope="Somente repete o texto recebido; sem acesso a sistemas externos",
        tools=(),
        permissions=(Permission.READ,),
        execution="em processo (thread do Agent Runtime)",
        timeout_seconds=5.0,
    )

    def run(self, ctx: AgentContext) -> AgentOutcome:
        task = ctx.task
        ctx.log(f"echo recebeu a tarefa {task.id}")
        text = f"echo: {task.title} | {task.objective}"
        return AgentOutcome(
            status="success",
            summary=text,
            usage={"input_chars": len(task.title) + len(task.objective), "output_chars": len(text)},
            cost=0.0,
        )

    def propose_split(self, task: Task) -> list[str]:
        """Proposta fixa, só para testar o fluxo de divisão aprovada (sem IA)."""
        return [f"Analisar: {task.title}", f"Executar: {task.title}", f"Validar: {task.title}"]
