"""Catálogo das áreas por setor e dos agentes planejados (PLANO_MESTRE, seções 3 e 5).

Dado estático e versionado: a aba Agentes, as telas "em breve" e, mais tarde, o Forge Bot
leem desta mesma fonte. Quando um agente planejado é implementado, ele sai daqui e passa a
existir na tabela `agents`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

SECTORS: tuple[tuple[str, str], ...] = (
    ("desenvolvimento", "Desenvolvimento"),
    ("juridico", "Jurídico"),
    ("financeiro", "Financeiro"),
)
# Agentes "comuns" aparecem na aba Agentes de todos os setores.
COMMON = "comum"

ENGINES = {
    "regra": "Sem IA",
    "haiku": "Haiku",
    "sonnet": "Sonnet",
    "haiku+sonnet": "Haiku + Sonnet",
    "regra+haiku": "Regra + Haiku",
    "regra+sonnet": "Regra + Sonnet",
    "busca+haiku": "Busca + Haiku",
    "sonnet+opus": "Sonnet (Opus opcional)",
}


@dataclass(frozen=True)
class PlannedAgent:
    id: str
    sector: str
    name: str
    summary: str
    description: str
    trigger: str
    engine: str
    writes: str
    phase: int


@dataclass(frozen=True)
class AreaTab:
    sector: str
    id: str
    label: str
    summary: str
    phase: int
    agents: tuple[str, ...] = ()


PLANNED: tuple[PlannedAgent, ...] = (
    # ---- Desenvolvimento -------------------------------------------------------------
    PlannedAgent(
        "triagem-issues", "desenvolvimento", "Triagem de issues",
        "Classifica a issue nova e liga às parecidas.",
        "Quando uma issue chega, sugere tipo, prioridade, área e size, e aponta issues "
        "parecidas já resolvidas (mesma base de issues/related.py). A sugestão aparece para "
        "revisão; aplicar labels no GitHub exige aprovação.",
        "Issue nova", "haiku", "Labels no GitHub, com aprovação", 1,
    ),
    PlannedAgent(
        "cacador-repeticao", "desenvolvimento", "Caçador de repetição",
        "Encontra o que se repete e propõe automação.",
        "Uma vez por semana lê issues, tarefas, investigações e logs de execução, agrupa o que "
        "aparece várias vezes e propõe uma automação para cada grupo, com estimativa de horas "
        "economizadas. Roda em lote, que custa metade.",
        "Semanal", "haiku+sonnet", "Não escreve", 1,
    ),
    PlannedAgent(
        "arquiteto", "desenvolvimento", "Arquiteto",
        "Revisa mudanças contra os ADRs e a teia de contexto.",
        "Lê o PR ou a proposta, compara com as decisões registradas (ADRs) e com a teia de "
        "contexto, e aponta desvio de arquitetura, acoplamento novo e código duplicado. "
        "Comentar no PR exige aprovação.",
        "PR aberto ou sob pedido", "sonnet", "Comentário no PR, com aprovação", 1,
    ),
    PlannedAgent(
        "revisor-pr", "desenvolvimento", "Revisor de PR",
        "Checklist de segurança e testes antes do merge.",
        "Procura segredo no diff, SQL de escrita, migration já aplicada sendo editada e "
        "comportamento novo sem teste. Devolve uma lista curta do que precisa de atenção.",
        "PR aberto", "sonnet", "Comentário no PR, com aprovação", 1,
    ),
    PlannedAgent(
        "notas-versao", "desenvolvimento", "Notas de versão",
        "Rascunho do CHANGELOG a partir dos commits.",
        "Lê os commits Conventional Commits desde a última tag e escreve a seção do CHANGELOG "
        "em português, agrupada por tipo. Quem opera revisa e cria a release.",
        "Sob pedido", "haiku", "Rascunho", 1,
    ),
    PlannedAgent(
        "documentador", "desenvolvimento", "Documentador",
        "Avisa quando a documentação ficou para trás.",
        "Depois de cada merge, compara o que mudou com os documentos que descrevem aquela "
        "parte e propõe a correção do texto. Abrir PR exige aprovação.",
        "Merge na main", "sonnet", "Rascunho de PR, com aprovação", 1,
    ),
    PlannedAgent(
        "monitor-conexoes", "desenvolvimento", "Monitor de conexões",
        "Avisa quando banco, FTP ou Portainer caem.",
        "Roda os probes das conexões cadastradas em intervalo fixo e avisa quando uma deixa de "
        "responder ou volta. Não usa IA.",
        "A cada N minutos", "regra", "Não escreve", 1,
    ),
    PlannedAgent(
        "guardiao-custos", "desenvolvimento", "Guardião de custos",
        "Soma o gasto de IA e pausa ao atingir o teto.",
        "Acompanha o custo por agente e por dia, avisa perto do limite e pausa o agente quando "
        "o teto é atingido. Não usa IA.",
        "Contínuo", "regra", "Pausa agentes do Forge", 1,
    ),
    # ---- Jurídico --------------------------------------------------------------------
    PlannedAgent(
        "pesquisa-base", "juridico", "Pesquisa na base",
        "Encontra peças, modelos e teses internas.",
        "Busca por assunto nas peças, modelos e teses do escritório e devolve os trechos "
        "relevantes com a fonte de cada um. A busca não usa IA; o resumo final usa Haiku.",
        "Sob pedido", "busca+haiku", "Não escreve", 6,
    ),
    PlannedAgent(
        "rascunho-peticao", "juridico", "Rascunho de petição",
        "Monta a peça a partir de modelo aprovado.",
        "Parte de um modelo aprovado e dos dados do caso, monta a peça e marca os campos que "
        "precisam de conferência. É sempre rascunho: a revisão do advogado é obrigatória.",
        "Sob pedido", "sonnet+opus", "Rascunho", 6,
    ),
    PlannedAgent(
        "controle-prazos", "juridico", "Controle de prazos",
        "Extrai prazos de publicações e cria lembretes.",
        "Lê publicações e intimações e extrai o prazo. A contagem de dias úteis e feriados é "
        "feita por regra, não por IA. Cria o lembrete para conferência do responsável.",
        "Publicação nova", "regra+haiku", "Lembrete", 6,
    ),
    PlannedAgent(
        "resumo-processo", "juridico", "Resumo de processo",
        "Linha do tempo do processo em poucas linhas.",
        "A partir dos andamentos, monta a linha do tempo do processo e um resumo do momento "
        "atual.",
        "Sob pedido", "haiku", "Não escreve", 6,
    ),
    PlannedAgent(
        "revisor-pecas", "juridico", "Revisor formal de peças",
        "Confere partes, documentos, valores e datas.",
        "Verifica se partes, CPF/CNPJ, valores e datas estão coerentes e se os pedidos batem "
        "com os fundamentos. Aponta o que conferir; não reescreve a peça.",
        "Sob pedido", "sonnet", "Não escreve", 6,
    ),
    PlannedAgent(
        "triagem-juridica", "juridico", "Triagem de e-mails jurídicos",
        "Separa intimação, cliente e tribunal.",
        "Classifica os e-mails do setor e sinaliza o que é urgente. Aplicar rótulo na caixa "
        "exige aprovação.",
        "E-mail novo", "haiku", "Rótulo, com aprovação", 6,
    ),
    # ---- Financeiro ------------------------------------------------------------------
    PlannedAgent(
        "alerta-vencimentos", "financeiro", "Alerta de vencimentos",
        "Avisa o que vence a pagar e a receber.",
        "Todos os dias lista o que vence em contas a pagar e a receber e cria os lembretes. "
        "Não usa IA.",
        "Diário", "regra", "Lembrete", 7,
    ),
    PlannedAgent(
        "leitor-documentos", "financeiro", "Leitor de documentos",
        "Extrai dados de boleto, nota e recibo.",
        "Lê o PDF e extrai valor, vencimento, CNPJ e linha digitável para conferência. Nada é "
        "lançado sem revisão.",
        "Arquivo novo", "haiku", "Não escreve", 7,
    ),
    PlannedAgent(
        "conciliacao", "financeiro", "Conciliação bancária",
        "Casa o extrato com os lançamentos.",
        "Concilia por regra (valor, data, documento). A IA só entra nos casos ambíguos, para "
        "sugerir o par mais provável.",
        "Diário", "regra+haiku", "Não escreve", 7,
    ),
    PlannedAgent(
        "regua-cobranca", "financeiro", "Régua de cobrança",
        "Rascunho de cobrança conforme o atraso.",
        "Escreve a mensagem de cobrança adequada a cada estágio de atraso. O envio só acontece "
        "com aprovação.",
        "Diário", "haiku", "E-mail, com aprovação", 7,
    ),
    PlannedAgent(
        "classificador-despesas", "financeiro", "Classificador de despesas",
        "Sugere categoria e centro de custo.",
        "Para cada lançamento novo, sugere categoria e centro de custo com base no histórico.",
        "Lançamento novo", "haiku", "Não escreve", 7,
    ),
    PlannedAgent(
        "fechamento-mensal", "financeiro", "Fechamento mensal",
        "Números do mês com um comentário curto.",
        "Os números são calculados sem IA. A IA só escreve o comentário sobre o que mudou em "
        "relação ao mês anterior.",
        "Mensal", "regra+sonnet", "Não escreve", 7,
    ),
    # ---- Comuns a todos os setores ---------------------------------------------------
    PlannedAgent(
        "triagem-email", COMMON, "Triagem de e-mail",
        "Classifica e prioriza a caixa do setor.",
        "Separa o que precisa de resposta, o que é informativo e o que pode esperar. Aplicar "
        "rótulo exige aprovação.",
        "E-mail novo", "haiku", "Rótulo, com aprovação", 5,
    ),
    PlannedAgent(
        "resumo-dia", COMMON, "Resumo do dia",
        "O que chegou e o que vence, em poucas linhas.",
        "Um resumo curto, de manhã, com o que chegou e o que vence no dia.",
        "Diário", "haiku", "Não escreve", 5,
    ),
    PlannedAgent(
        "rascunho-resposta", COMMON, "Rascunho de resposta",
        "Propõe a resposta; nunca envia sozinho.",
        "Escreve uma proposta de resposta para o e-mail escolhido. Quem envia é a pessoa.",
        "Sob pedido", "haiku", "Rascunho", 5,
    ),
    PlannedAgent(
        "lembretes", COMMON, "Lembretes",
        "Avisos agendados por pessoas ou por outros agentes.",
        "Guarda e dispara lembretes no sistema e por e-mail, conforme as preferências em "
        "Configurações › Lembretes. Não usa IA.",
        "Agenda", "regra", "Não escreve", 5,
    ),
)

# Abas que ainda não têm conteúdo (as que já existem ficam no frontend).
TABS: tuple[AreaTab, ...] = (
    AreaTab("desenvolvimento", "email", "E-mail",
            "Caixa do setor com triagem, resumo do dia e rascunhos de resposta.", 5,
            ("triagem-email", "resumo-dia", "rascunho-resposta")),
    AreaTab("desenvolvimento", "notas", "Notas",
            "Hoje as notas ficam dentro de Investigação. Aqui terão uma tela própria, por setor.", 5),
    AreaTab("juridico", "pecas", "Peças e modelos",
            "Peças, modelos e teses do escritório, com busca por assunto.", 6,
            ("pesquisa-base", "rascunho-peticao", "revisor-pecas")),
    AreaTab("juridico", "prazos", "Prazos",
            "Prazos extraídos das publicações, com lembrete para o responsável.", 6,
            ("controle-prazos", "resumo-processo")),
    AreaTab("juridico", "email", "E-mail",
            "Caixa do setor com triagem de intimações, clientes e tribunais.", 5,
            ("triagem-juridica", "resumo-dia", "rascunho-resposta")),
    AreaTab("juridico", "notas", "Notas",
            "Anotações do setor, separadas das de outros setores.", 5),
    AreaTab("financeiro", "contas", "Contas e vencimentos",
            "Contas a pagar e a receber, com alerta de vencimento.", 7,
            ("alerta-vencimentos", "leitor-documentos", "conciliacao", "regua-cobranca")),
    AreaTab("financeiro", "relatorios", "Relatórios",
            "Fechamento mensal e indicadores do setor.", 7,
            ("fechamento-mensal", "classificador-despesas")),
    AreaTab("financeiro", "email", "E-mail",
            "Caixa do setor com triagem e régua de cobrança.", 5,
            ("triagem-email", "regua-cobranca", "rascunho-resposta")),
    AreaTab("financeiro", "notas", "Notas",
            "Anotações do setor, separadas das de outros setores.", 5),
)


def catalog() -> dict:
    """Visão pública do catálogo: setores, abas futuras e agentes planejados."""
    return {
        "sectors": [{"id": sid, "label": label} for sid, label in SECTORS],
        "common": COMMON,
        "engines": dict(ENGINES),
        "tabs": [asdict(tab) for tab in TABS],
        "planned": [asdict(agent) for agent in PLANNED],
    }
