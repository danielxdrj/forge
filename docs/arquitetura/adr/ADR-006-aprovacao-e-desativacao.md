# ADR-006: Aprovação humana e desativação

- **Status:** Proposto, aguardando aprovação do responsável
- **Data:** 2026-11-06
- **Revisar quando:** a política de aprovação detalhada for definida

## Contexto
Independência operacional exige que tudo seja desativável com procedimento manual; operações críticas exigem humano.

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| Aprovação em toda ação | Máxima segurança | Atrito alto, ferramenta pouco usada |
| Aprovação só para escrita/crítico; leitura livre | Equilíbrio | Exige classificar operações |
| Sem aprovação | Rápido | Inaceitável para escrita externa |

## Recomendação
Leitura sem aprovação; escrita remota, release, deploy e SQL de escrita com aprovação registrada em Audit Logs. Cada agente tem `ativo`; há chave global; cada um aponta para procedimento manual. Padrão já usado: `RELEASE_AUTOMATION_ENABLED`.

## Consequências
Manutenção: precisa manter a lista de operações críticas. Segurança: alta. Custo: tempo humano nas aprovações.
