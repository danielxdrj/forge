# 04 — Conexão e cofre

Estado: bloqueada.

## Objetivo e contexto

Cadastrar uma conexão sem gravar o segredo no Git e recuperar esse segredo só pelo adaptador que precisar dele.

## Problema que resolve

As consultas futuras precisam saber qual sistema existe sem colocar a credencial no repositório, nos logs ou nos prompts.

## Pré-requisitos

- Etapa 01 concluída, para existir aplicação e persistência.
- Mecanismo do cofre escolhido.

Não depende de log nem de LLM.

## Escopo incluído

- Cadastro da conexão: nome, tipo, destino e referência do segredo.
- Um cofre local.
- A separação entre configuração e segredo.

## Escopo excluído

A consulta real ao sistema externo, se ela ainda depender de um protocolo não escolhido. O valor do segredo não faz parte do cadastro guardado no Git.

## Cofre

Opções já registradas, sem escolha:

- Variáveis de ambiente em arquivo local ignorado pelo Git.
- Cofre do sistema operacional.
- Arquivo cifrado fora do repositório.

A escolha não deve vazar para os casos de uso. As três podem implementar a mesma porta. Essa porta continua hipótese.

## Critérios de aceite

- O segredo de exemplo não aparece no diretório versionado nem num log da operação de cadastro.
- Um teste demonstra a separação entre configuração e segredo.

## Testes esperados

O teste usa placeholder, nunca credencial real. Ele confere que o valor não está no cadastro persistido nem na saída da operação.

## Documentação a atualizar

`docs/ARCHITECTURE.md`, `docs/PRODUCT.md`, `docs/ROADMAP.md` e esta especificação.

## Riscos

Um exemplo com segredo real, ou um log da URL e do cofre, quebra a regra permanente de credenciais.

## Decisões pendentes

O mecanismo do cofre.

## Aprovação

Depende da etapa 01 concluída e de autorização explícita.
