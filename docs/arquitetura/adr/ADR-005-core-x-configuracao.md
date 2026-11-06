# ADR-005: Separação entre Forge Core e configuração da empresa

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** a configuração crescer a ponto de exigir ciclo de revisão próprio

## Contexto
Agentes, prompts, permissões e políticas são da empresa; o motor é genérico. Segredos nunca no Git.

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| Tudo no mesmo repositório, em pasta `config/` | Um PR, simples | Mistura código e política; revisão e permissões iguais |
| Repositório de configuração separado, versionado | Revisão e dono próprios; Core reutilizável | Dois repositórios e versões a sincronizar |
| Configuração só no banco/UI | Edição fácil | Sem histórico por PR; difícil de transferir |

## Recomendação
Repositório de configuração separado (ou pasta isolada com CODEOWNERS, se o responsável preferir um só). Segredos ficam em cofre institucional; a configuração só referencia onde estão. Schema da configuração é versionado no Core.

## Consequências
Manutenção: média. Segurança: mudança de permissão de agente passa por revisão. Custo: nulo.
