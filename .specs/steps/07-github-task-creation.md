# 07 — Publicação de tarefa no GitHub

Estado: bloqueada.

Direção aceita. Não é a próxima implementação e não tem data.

## Objetivo e contexto

Receber uma solicitação, preparar uma descrição estruturada, apresentar a tarefa para revisão e publicá-la no GitHub somente depois de aprovação explícita.

## Problema que resolve

Hoje a pessoa interpreta a solicitação, escreve título e descrição e preenche o GitHub Projects à mão.

## Pré-requisitos

Autorização explícita desta etapa. Não depende dos conectores de leitura.

Também é preciso confirmar os campos do Project, a conta responsável, como identificar a sprint vigente e as opções de tipo, prioridade, escopo e status.

## Escopo incluído

Quando for autorizada e desbloqueada:

- Representar a solicitação e a descrição estruturada.
- Receber texto. Imagem fica para uma decisão posterior. Upload não está aprovado.
- Gerar título, descrição e campos sugeridos para revisão.
- Publicar a issue e preencher os campos do Project só depois da aprovação explícita.

O modelo de descrição já indicado é:

- Solicitado por
- Objetivo
- Contexto
- Situação atual
- Escopo
- Comportamento esperado
- Critérios de aceite
- Observações

## Escopo excluído

Alterar o código do sistema de trabalho. Push, pull request, correção e deploy. Publicar sem aprovação. Escolher IDs internos, opções ou nome de usuário que não estejam escritos nesta especificação.

A leitura de repositório e metadados, se existir, continua na etapa 06. Não misturar as duas.

## Como a geração acontece

Não está decidido. Um LLM poderia redigir a descrição, e a etapa 03 ainda não existe. Sem esse mecanismo, a etapa não deve inventar a geração. Esta é uma decisão essencial.

## Campos do GitHub Projects

Citados no fluxo atual e ainda não confirmados:

- Assignee: a própria conta de quem opera. O identificador da conta não está registrado.
- Sprint: a sprint vigente, identificada na hora. Não usar valor fixo.
- Size: o fluxo atual cita `3`. Isso não está confirmado como regra.
- Tipo, prioridade, escopo e status inicial. Os nomes das opções não estão registrados.

Nenhum identificador interno da API do GitHub está definido. Não presumir.

## Critérios de aceite

Ainda não fechados, porque os campos não estão confirmados. O mínimo já definido é:

- A tarefa não é publicada antes da aprovação explícita.
- A publicação não altera código do sistema de trabalho.
- Segredo não aparece no texto publicado nem nos logs.

## Testes esperados

Um teste com cliente falso do GitHub mostra que, sem aprovação, não há publicação. Outro mostra que a aprovação publica a issue e os campos confirmados. Não usar token real.

## Documentação a atualizar

`docs/PRODUCT.md`, `docs/ROADMAP.md`, `AGENTS.md` se a exceção de escrita mudar, e esta especificação.

## Riscos

Token do GitHub é credencial. Ele segue a regra do cofre e não entra no Git, nos logs nem nos prompts. Publicar cedo demais escreve num sistema externo.

## Decisões pendentes

1. Como o título e a descrição são gerados.
2. Se a entrada pode ser imagem, e como, já que upload não está aprovado.
3. Conta responsável, método da sprint vigente e opções reais de tipo, prioridade, escopo, status e size.
4. Onde a tarefa em revisão fica guardada antes da publicação.

## Aprovação

Exige autorização própria. Enquanto estiver bloqueada, nenhuma escrita no GitHub é permitida.
