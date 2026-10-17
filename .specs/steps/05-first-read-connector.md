# 05 — Primeiro conector somente leitura

Estado: bloqueada.

## Objetivo e contexto

Provar a porta de leitura com uma fonte externa real e simples, gravando o resultado como evidência. O arquivo de log local da etapa 02 não é essa fonte.

## Problema que resolve

O Forge só se torna um copiloto de sistemas técnicos quando uma consulta autorizada entra na investigação sem um caso especial dentro do núcleo.

## Pré-requisitos

- Etapa 02 concluída, porque o resultado vira evidência.
- A primeira fonte externa escolhida.
- O que conta como leitura nessa fonte.
- Etapa 04 concluída somente se essa fonte usar segredo. Um diretório local pode não precisar de cofre.

## Escopo incluído

Um único adaptador, sem método de escrita, e o uso explícito dessa leitura dentro de uma investigação.

## Escopo excluído

As outras integrações. Correção de código, deploy e mudança de configuração.

## Candidatas já registradas

Não há escolha. As candidatas coerentes com o aprendizado são um diretório local tratado como fonte externa, ou o primeiro sistema do trabalho que já tenha acesso de leitura. O log da etapa 02 não responde a essa escolha.

## Critérios de aceite

- Uma consulta pedida pelo operador vira evidência na investigação.
- O adaptador não oferece operação de alteração.
- Investigação, evidência e análise não mudam de significado para caber essa fonte.

## Testes esperados

Um teste com fonte fictícia cobre a leitura e a evidência gravada. Não usa credencial real.

## Documentação a atualizar

`docs/ARCHITECTURE.md`, `docs/ROADMAP.md` e esta especificação. Se o núcleo precisar mudar, a mudança é explícita e justificada aqui.

## Riscos

Tratar escrita como “leitura administrativa”. O contrato do conector não oferece escrita.

## Decisões pendentes

1. Qual é a primeira fonte externa.
2. Quais operações dessa fonte contam como leitura.

## Aprovação

Depende da etapa 02 concluída e de autorização explícita. Depende da etapa 04 quando a fonte escolhida usar segredo.
