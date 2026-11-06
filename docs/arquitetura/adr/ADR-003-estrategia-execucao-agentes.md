# ADR-003: Estratégia de execução dos agentes

- **Status:** Aprovado com ajuste (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** FRG-46 for concluída, ou o LLM/fornecedor for escolhido

## Contexto
Agentes seguem o contrato mínimo (seção 5 do documento). O fornecedor de LLM e a ferramenta de agente não estão decididos.

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| Runtime próprio fino, com adaptador para o motor (LLM ou agente de código) | Contrato, permissões e logs sob controle da empresa; troca de motor sem mudar agentes | Código próprio para manter |
| Delegar tudo a uma ferramenta/framework de agentes pronta | Menos código | Dependência de fornecedor; permissões e auditoria dependem da ferramenta; risco de continuidade |
| Fluxos em n8n | Visual, baixo código | n8n é opcional e futuro; lógica fora do Git tende a ficar opaca |

## Recomendação
Runtime próprio fino: aplica o contrato, ferramentas autorizadas, limites, redação e logs, e chama o motor por um adaptador. Execução que altera código roda isolada (diretório/contêiner descartável). Escolha do motor fica aberta.

## Consequências
Manutenção: média, compensada por contrato estável. Segurança: controle central de permissões. Custo: limite por execução no próprio runtime.

## Ajuste aprovado
A direção é provisória e será revista depois da FRG-46. LLM/fornecedor e motor de execução continuam em aberto.
