# 02 — Evidência de log local

Estado: concluída.

## Objetivo e contexto

Anexar a uma investigação a evidência vinda de um arquivo de log local. O caso de uso mais amplo do Forge inclui esse log. A etapa 01 não o implementa.

## Problema que resolve

Uma investigação só com título não guarda o fato que motivou o diagnóstico.

## Pré-requisitos

- Etapa 01 concluída.

## Escopo incluído

A ligação entre a investigação e essa evidência. A investigação reaberta mostra a evidência anexada.

## Escopo excluído

Leitura de sistema externo, análise por LLM, upload genérico além do que for decidido para o log, e união desta etapa com a etapa 01. Essa união foi proposta e não foi aprovada.

## Proposta anterior, substituída

A primeira versão do roadmap pedia evidência manual: um texto colado pelo operador, com origem “manual” e o momento do anexo. A decisão posterior trocou a fonte por um arquivo de log local. O texto colado não é o requisito atual. Permanece aqui para não parecer apagado.

A imutabilidade da evidência depois de registrada também estava nessa versão. A arquitetura ainda a trata como hipótese, não como regra aprovada.

## Como o log entra

O texto do log chega no JSON de `POST /investigations/{investigation_id}/evidence`. A API não recebe caminho de disco, não faz upload de arquivo e não usa credencial. Credenciais e tokens ficam para uma correção posterior.

O que fica gravado é o texto inteiro, a origem `local_log` definida pelo servidor, o momento e a ligação com a investigação. Não ficam caminho nem nome de arquivo.

Esta etapa não oferece alteração nem exclusão da evidência. A hipótese de imutabilidade continua sem uma regra extra no banco.

## Critérios de aceite

- A investigação reaberta mostra a evidência que foi anexada.
- Um teste cobre esse comportamento.
- A evidência não é lida de banco, FTP, GitHub ou Portainer.

## Testes esperados

Um teste anexa a evidência do modo que for aprovado e consulta a investigação de novo. O resultado mostra essa evidência.

## Documentação a atualizar

`docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LEARNING_GUIDE.md` e esta especificação.

## Riscos

Um log pode ser grande e pode conter segredo. O que fica gravado é decisão essencial, não detalhe de implementação.

## Decisões pendentes

1. Tamanho máximo do texto. Um log grande continua sendo um risco deixado para correção posterior.
2. Se a evidência, uma vez registrada, pode ser alterada. Isso continua hipótese.

## Aprovação

Depende da etapa 01 concluída e de autorização explícita. Não começa junto com a etapa 01.
