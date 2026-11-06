# ADR-007: Integração com GitHub

- **Status:** Aprovado com ajuste (06/11/2026)
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

## Ajuste aprovado
Depende de criar a organização no GitHub, pois hoje o repositório está em conta pessoal. Até a migração, usar solução temporária sem token pessoal de longa duração (por exemplo, credencial de curta duração emitida sob demanda por quem opera, com escopo mínimo, ou apenas o `GITHUB_TOKEN` dos workflows). A FRG-21 formaliza a escolha entre GitHub App e token fine-grained.
