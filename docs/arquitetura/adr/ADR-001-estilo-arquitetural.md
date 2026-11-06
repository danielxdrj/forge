# ADR-001: Estilo arquitetural

- **Status:** Proposto, aguardando aprovação do responsável
- **Data:** 2026-11-06
- **Revisar quando:** houver necessidade de escalar ou implantar partes de forma independente

## Contexto
Ferramenta interna, equipe pequena, continuidade exige simplicidade. Nada implementado ainda.

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| Monólito modular (um processo, módulos com fronteiras claras) | Simples de operar, depurar e transferir; um deploy; custo baixo | Falha de um módulo afeta o processo; exige disciplina nas fronteiras |
| Serviços separados | Isolamento e escala independentes | Mais deploys, rede, observabilidade; manutenção e custo maiores sem necessidade hoje |

## Recomendação
Monólito modular. Módulos = componentes da seção 4; dependência só via interfaces. Separar em serviço depois, se houver motivo medido.

## Consequências
Manutenção: baixa. Segurança: superfície única; isolar execução de agentes (ADR-003). Custo: mínimo.
