# Protocolo de execução

Estas instruções valem quando alguém autoriza uma etapa do [plano](IMPLEMENTATION_PLAN.md). Autorizar uma etapa não autoriza a seguinte.

A branch-base é `main`.

## Antes de alterar o repositório

1. Ler `.specs/PROJECT_CONTEXT.md`, `.specs/IMPLEMENTATION_PLAN.md`, `.specs/EXECUTION_PROTOCOL.md`, a especificação da etapa, `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` e `docs/PRODUCT.md`.
2. Inspecionar o estado real: branch atual, `git status`, histórico recente e diferenças existentes.
3. Confirmar pré-requisitos e decisões aprovadas da etapa. Não sobrescrever trabalho existente nem descartar alterações locais.
4. Se a etapa estiver `bloqueada` por decisão essencial, parar e perguntar. Não escolher a pendência em silêncio.
5. Se a etapa não for a autorizada, não implementá-la.

## Branch

Criar a branch a partir de `main` atualizada, somente se ela ainda não existir.

O nome segue o identificador da etapa e o tipo do Conventional Commit dominante. Exemplo da etapa 01: `feat/01-create-and-read-investigation`.

Se a branch já existir, usá-la. Não criar uma segunda branch paralela para a mesma etapa.

## Durante a implementação

6. Implementar só o escopo incluído na especificação.
7. Separar o trabalho em blocos coerentes, relacionados e testáveis.
8. Executar os testes, as verificações e os critérios de aceite da especificação.
9. Revisar o diff completo. Atualizar a documentação citada na etapa, inclusive o estado no plano e na especificação.
10. Um problema não essencial segue a decisão já escrita. Registrar a escolha na especificação. Um problema essencial interrompe a implementação.

## Commits, push e pull request

11. Criar commits Conventional Commits, um por bloco lógico. Não incluir alteração fora do bloco.
12. Fazer `git push -u origin HEAD` somente se o remoto estiver configurado, os testes exigidos tiverem passado e o push estiver autorizado.
13. Preparar o material do Pull Request: resumo, motivação, mudanças, testes e limitações.

Não fazer merge. Não abrir a próxima etapa. Não contornar teste que falhou. Não usar operação destrutiva de Git para resolver conflito.

## Encerramento

A etapa termina quando os critérios de aceite são verdadeiros e os documentos afetados foram atualizados. O relatório final diz o que foi feito, o que ficou de fora, o resultado dos testes e qual decisão continua aberta.

O estado passa a `concluída` só nesse momento. Até lá, `em andamento` enquanto a branch da etapa tiver trabalho não encerrado.
