# 06 — Integrações de leitura seguintes

Estado: bloqueada.

## Objetivo e contexto

Adicionar outra fonte sem mudar o significado de investigação, evidência e análise. Cada sistema restante repete essa etapa. O detalhe do que é leitura naquele sistema só é escrito quando a etapa dele começar.

## Problema que resolve

Uma segunda fonte mostra se a porta da etapa 05 serve para mais de um sistema.

## Pré-requisitos

- Etapa 05 concluída.
- A próxima fonte escolhida, uma por vez.
- O mapeamento de leitura dessa fonte.

## Escopo incluído

Só o adaptador novo e os testes dele.

## Escopo excluído

Redesenho do núcleo. Se o núcleo precisar mudar para caber a segunda fonte, a porta da etapa 05 ficou estreita e o ajuste é explícito. Correção de código, deploy e mudança de configuração continuam fora.

## Fontes já citadas, sem ordem

A ordem entre elas não está definida. Cada uma entra quando for escolhida.

- Banco de dados externo. Pendente: qual produto e quais comandos são leitura. Este banco não é o PostgreSQL do Forge.
- FTP/SFTP. Pendente: quais diretórios podem ser listados e baixados. Sem envio e sem remoção.
- GitHub, como leitura. Pendente: quais repositórios e quais metadados entram. Sem push e sem abrir pull request. A publicação de tarefa é a etapa 07, não esta leitura.
- Portainer. Pendente: quais ambientes e quais informações de container ou stack entram. Sem reiniciar, alterar stack ou mudar configuração.

## Critérios de aceite

- As duas fontes, a da etapa 05 e a nova, alimentam evidência pelo mesmo caso de uso.
- O adaptador novo não oferece escrita.

## Testes esperados

Testes do adaptador novo, com dados fictícios, mais o caso de uso de evidência já existente.

## Documentação a atualizar

`docs/ROADMAP.md`, `docs/ARCHITECTURE.md` e uma especificação própria da fonte, criada no início dessa repetição. Esta página permanece o índice das fontes ainda não escolhidas.

## Riscos

Implementar várias fontes no mesmo pedido. A regra é uma fonte por etapa autorizada.

## Decisões pendentes

A ordem e, para cada fonte, as pendências listadas acima.

## Aprovação

Depende da etapa 05 concluída. Cada repetição precisa de autorização própria.
