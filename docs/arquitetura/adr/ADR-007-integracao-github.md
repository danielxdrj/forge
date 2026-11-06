# ADR-007: Integração com GitHub

- **Status:** Proposto, aguardando aprovação do responsável
- **Data:** 2026-11-06
- **Revisar quando:** mudar o repositório/organização ou o modelo de credenciais

## Contexto
Credenciais devem ser institucionais, não de conta pessoal. Hoje o repositório está em conta pessoal ([Fato], FRG-9, seção 7).

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| GitHub App da organização | Escopo mínimo por repositório, tokens curtos, independe de pessoa | Configuração inicial; exige organização |
| Token pessoal (PAT) | Rápido | Atrelado a pessoa; permissões amplas; viola continuidade |
| Conta de serviço com PAT | Simples | Token longo, escopo mais difícil de limitar |

## Recomendação
GitHub App da organização, começando só com leitura; escrita (branch/PR) liberada depois, com aprovação (ADR-006). Depende de existir organização e dono institucional (pergunta 7).

## Consequências
Manutenção: baixa após configurar. Segurança: menor privilégio e rotação automática. Custo: nenhum.
