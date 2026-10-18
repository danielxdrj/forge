# Contexto do projeto

Fonte operacional do Forge. Explica o produto e as regras que valem para todas as etapas. O detalhe de cada etapa está em [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). A narrativa de produto, arquitetura e aprendizagem permanece em `docs/`.

## Objetivo e visão

O Forge é um copiloto de engenharia local. Ele existe para cadastrar conexões com sistemas técnicos, consultar fontes autorizadas, registrar investigações e, numa etapa posterior, usar um LLM para ajudar no diagnóstico.

O resultado de uma análise é sugestão. O Forge não corrige código nem altera produção por conta própria.

## Problema

Diagnosticar um problema de software exige juntar fatos de vários lugares. Feito à mão, o contexto se espalha. Pedir ajuda a um LLM sem registro mistura evidência, segredo e palpite.

## Usuário e ambiente

O uso aprovado é individual, nesta máquina. Não há papéis nem permissões. Mais de uma pessoa na mesma instalação está fora do escopo atual.

A branch-base do projeto é `main`. Trabalho novo sai dela, pelo protocolo em [EXECUTION_PROTOCOL.md](EXECUTION_PROTOCOL.md).

## Stack e decisões aprovadas

- Linguagem do backend: Python.
- Linguagem da tela: JavaScript. React desenha a interface, Tailwind define o tema e o Vite gera os arquivos estáticos.
- Backend: FastAPI, executado na máquina na primeira implementação.
- Persistência dos dados do próprio Forge: PostgreSQL, no serviço `postgres`.
- Projeto do Compose: `forge_system`.
- Serviços previstos: `backend`, `frontend` e `postgres`.
- O Compose sobe `postgres` e `frontend`. O `backend` alcança o banco por `localhost`.
- O nome `postgres` é o endereço quando o `backend` também estiver na rede do Compose.
- A documentação interativa do FastAPI continua sendo o uso da API. A tela do `frontend` existe e ainda não chama a API.
- A tela mostra a navegação de investigação, automações, log local, conexões e configurações. As listas ficam vazias. Os tipos de conexão visíveis são banco de dados, FTP/SFTP, repositório Git e Portainer, sem cadastro gravado.
- A primeira funcionalidade cria uma investigação e a consulta pelo identificador.
- Os campos desse primeiro registro são identificador, título e data de criação.
- As rotas previstas são `POST /investigations` e `GET /investigations/{investigation_id}`.

O identificador é um número gerado pelo PostgreSQL. O título tem no máximo 200 caracteres. O banco e o usuário se chamam `forge`. A senha fica no ambiente, ainda sem valor. A API não tem endereço padrão: `FORGE_HOST` e `FORGE_PORT` são definidos no ambiente.

## Arquitetura prevista

O `backend` é um programa só. Os containers separam a interface, a API e o banco. Um container por integração não faz parte do desenho atual.

A hipótese ainda não implementada é separar rotas, casos de uso e portas. PostgreSQL é o armazenamento aprovado. Conector, LLM e cofre não entram no código enquanto a etapa correspondente não estiver ativa.

O `postgres` do Forge guarda os dados do próprio sistema. Um banco externo, se for consultado numa investigação, será outro conector, somente leitura.

Detalhe e diagrama: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Requisitos funcionais

Já pedidos para o produto, cada um na sua etapa:

- Registrar uma investigação e reabri-la.
- Anexar evidência vinda de um arquivo de log local.
- Pedir uma análise ao LLM e guardá-la como sugestão. Uma etapa posterior, ainda sem abertura, pode aplicar essa sugestão depois de aprovação: o Cursor altera o código ou devolve o SQL para alterar o banco. O SQL volta como texto e não é executado. Se a alteração for de código, uma segunda aprovação vem antes de criar o commit e enviar a branch.
- Cadastrar uma conexão sem gravar o segredo no Git.
- Consultar uma fonte autorizada em modo somente leitura e guardar o resultado como evidência.
- Acrescentar integrações sem redefinir o que é uma investigação.
- Numa etapa futura, preparar uma tarefa estruturada e publicá-la no GitHub somente depois de aprovação explícita, sem alterar o código do sistema de trabalho.

A primeira implementação cobre só criar e consultar a investigação.

## Requisitos não funcionais

- O projeto começa local. Hospedagem remota é etapa futura e não herda autenticação nem exposição de segredos.
- Simplicidade, segurança, testabilidade e manutenção vêm antes de abrangência.
- Uma integração nova não deve reescrever o núcleo.
- Credenciais não entram no código, nos logs, nos prompts enviados ao LLM nem no Git.
- Toda integração externa nasce somente leitura, com a exceção futura da publicação de tarefa no GitHub.

## Restrições de segurança

- Não alterar sistemas conectados: SQL de escrita, upload, delete, push, pull request, comentário, restart ou edição remota.
- Não corrigir código de outro sistema e não alterar produção.
- Não executar a sugestão do LLM enquanto a etapa posterior de aplicação não estiver ativa. Nessa etapa, ainda sem abertura, o Cursor pode alterar o código depois de aprovação, ou devolver o SQL sem executá-lo. O commit e o envio da branch pedem uma segunda aprovação.
- A publicação no GitHub só vale na etapa 07, depois de aprovação explícita de quem opera.
- Exemplos usam placeholders. Testes usam dados fictícios.
- A senha do PostgreSQL fica no ambiente.

## Fora do escopo da primeira implementação

LLM, conexões externas, cofre, a ligação da tela com a API, imagem Docker do `backend`, upload, análise de log e publicação no GitHub.

Também estão fora do produto atual: SLA, multiempresa, aplicativo móvel, marketplace de conectores e execução autônoma de ferramentas pelo modelo.

## Decisões pendentes

A etapa 01 não tem mais decisão essencial aberta. A senha do PostgreSQL e o endereço da API ficam no ambiente, vazios até serem preenchidos.

Bloqueiam etapas posteriores, listadas no plano:

1. Como o log chega à API e o que dele fica gravado.
2. Qual programa nesta máquina escreve a análise. Já está decidido que o texto fica na máquina, que quem opera confirma o contexto antes do envio, e que a resposta tem estrutura fixa com a sugestão de correção. A aplicação dessa sugestão fica para uma etapa posterior.
3. Mecanismo do cofre.
4. O que significa fonte autorizada.
5. Primeira fonte externa e o que conta como leitura em cada sistema.
6. Campos do GitHub Projects, conta responsável, sprint vigente e opções de tipo, prioridade, escopo e status.
7. Campos adicionais de uma investigação no dia a dia.

Critérios de sucesso do produto estão propostos em [docs/PRODUCT.md](../docs/PRODUCT.md) e ainda não foram aceitos.

## Relação com os outros documentos

| Documento | Papel |
| --- | --- |
| `.specs/` | O que executar, em qual ordem, e como uma IA conduz a etapa. |
| [README.md](../README.md) | Porta de entrada. |
| [AGENTS.md](../AGENTS.md) | Regras permanentes. Aponta para este diretório. |
| [docs/PRODUCT.md](../docs/PRODUCT.md) | Problema, usuários, capacidades e limites. |
| [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) | Forma do sistema, hipóteses e fronteiras. |
| [docs/ROADMAP.md](../docs/ROADMAP.md) | Índice legível das etapas, com o que entra, o que fica de fora e o que está pendente. |
| [docs/LEARNING_GUIDE.md](../docs/LEARNING_GUIDE.md) | Conceitos e o código que já existe. |
| [docs/IMPLEMENTATION_PLAN.md](../docs/IMPLEMENTATION_PLAN.md) | Atalho para o plano operacional. O texto executável está aqui em `.specs/`. |

Se uma decisão mudar, atualize este arquivo, o plano, a etapa afetada e o documento em `docs/` que explica essa decisão. Não mantenha duas versões divergentes.
