# Plano de implementação

Índice das etapas. O detalhe executável está no arquivo de cada etapa. As etapas 01 e 02 estão concluídas. As seguintes continuam bloqueadas.

A ordem segue o [roadmap](../docs/ROADMAP.md). Uma alternativa considerada no início, ligar um conector real antes de qualquer LLM, não foi adotada. Outra proposta antiga, anexar texto colado à mão, foi substituída pela evidência de log local. As duas permanecem registradas na etapa correspondente. Não são requisitos descartados em silêncio: uma foi preterida, a outra mudou de fonte.

A proposta de nomes `01-investigation-crud` e `03-investigation-history` não foi usada. O repositório não pede alteração nem exclusão de investigação, e reabrir um caso conhecido já faz parte da etapa 01. Não há etapa separada de histórico.

A branch-base é `main`.

| Id | Etapa | Estado | Depende de | Especificação |
| --- | --- | --- | --- | --- |
| 00 | Documentação inicial | concluída | — | os documentos atuais do repositório |
| 01 | Criar e consultar uma investigação | concluída | 00 concluída | [steps/01-create-and-read-investigation.md](steps/01-create-and-read-investigation.md) |
| 02 | Evidência de log local | concluída | 01 concluída | [steps/02-local-log-evidence.md](steps/02-local-log-evidence.md) |
| 03 | Análise por LLM | bloqueada | 02 concluída | [steps/03-llm-analysis.md](steps/03-llm-analysis.md) |
| 04 | Conexão e cofre | bloqueada | 01 concluída | [steps/04-connections-and-vault.md](steps/04-connections-and-vault.md) |
| 05 | Primeiro conector somente leitura | bloqueada | 02 concluída; 04 se a fonte usar segredo | [steps/05-first-read-connector.md](steps/05-first-read-connector.md) |
| 06 | Integrações de leitura seguintes | bloqueada | 05 concluída | [steps/06-additional-read-connectors.md](steps/06-additional-read-connectors.md) |
| 07 | Publicação de tarefa no GitHub | bloqueada | autorização explícita; não é a próxima etapa | [steps/07-github-task-creation.md](steps/07-github-task-creation.md) |
| 08 | Hospedagem remota | bloqueada | uso local aceito | [steps/08-remote-hosting.md](steps/08-remote-hosting.md) |

A etapa 04 não precisa do log nem do LLM. A etapa 05 grava o resultado como evidência, então precisa da etapa 02. Ela só precisa do cofre se a fonte escolhida usar segredo. Uma das candidatas é um diretório local, que pode não ter credencial. A etapa 07 não depende dos conectores de leitura. Ela continua fora da frente de implementação até ser autorizada.

Estado `bloqueada` significa que a direção existe e o código não começa enquanto a especificação listar decisão essencial em aberto.
