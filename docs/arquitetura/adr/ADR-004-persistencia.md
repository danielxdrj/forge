# ADR-004: Tecnologia de persistência

- **Status:** Proposto, aguardando aprovação do responsável
- **Data:** 2026-11-06
- **Revisar quando:** a stack for definida ou o volume/concorrência mudar

## Contexto
Armazenar tarefas, estados, aprovações, resultados e auditoria. O banco não foi decidido; o legado usa PostgreSQL, mas não deve orientar a escolha (FRG-9).

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| PostgreSQL | Robusto, concorrência, backup e ferramentas conhecidos; serve a auditoria | Serviço a operar, credenciais, backup |
| SQLite | Zero operação, um arquivo | Concorrência limitada; backup e acesso remoto manuais; migração futura |
| Arquivos (JSON/Markdown) no Git | Transparente, versionado | Sem consulta nem integridade; ruim para estado e auditoria |

## Recomendação
PostgreSQL, atrás de uma interface de repositório e com migrações versionadas desde o início. Justificativa: estado e auditoria exigem integridade e múltiplos processos (API + execuções). **[Opinião]** SQLite é aceitável para o primeiro protótipo se o responsável preferir menos operação.

## Consequências
Manutenção: média (backup, migração). Segurança: segredo do banco fora do Git, usuário com menor privilégio; auditoria sem permissão de update/delete. Custo: baixo.
