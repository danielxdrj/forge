# 08 — Hospedagem remota

Estado: bloqueada.

## Objetivo e contexto

Levar o Forge para além da máquina local, somente depois que o uso local estiver aceito.

## Problema que resolve

O projeto pode precisar de hospedagem remota no futuro. Essa necessidade não está especificada.

## Pré-requisitos

Uso local aceito. Documento próprio de autenticação, exposição de rede e lugar dos segredos. Esse documento ainda não existe.

## Escopo incluído

Nada está incluído. A etapa não herda usuários, autenticação nem exposição dos segredos do uso local.

## Escopo excluído

Antecipar autenticação, rede pública ou cofre remoto nas etapas locais.

## Critérios de aceite

Não definidos. Serão escritos quando a etapa for aberta.

## Testes esperados

Não definidos.

## Documentação a atualizar

Um documento próprio, mais `docs/ARCHITECTURE.md` e `docs/ROADMAP.md`.

## Riscos

Tratar a hospedagem como continuação automática do uso individual nesta máquina.

## Decisões pendentes

Todas as de hospedagem: quem acessa, como autentica, o que fica exposto e onde os segredos ficam.

## Aprovação

Depende do uso local aceito e de autorização explícita para abrir a etapa.
