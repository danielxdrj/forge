# 01 — Criar e consultar uma investigação

Estado: bloqueada.

A direção está aprovada. O código não começa enquanto as decisões essenciais abaixo estiverem abertas.

## Objetivo e contexto

Persistir uma investigação no PostgreSQL do Forge e recuperá-la pelo identificador. Esta é a primeira funcionalidade de código. Não há aplicação no repositório.

## Problema que resolve

Sem um registro reabrível, o restante do copiloto não tem onde guardar evidência nem análise.

## Pré-requisitos

- Etapa 00 concluída.
- Python, FastAPI e PostgreSQL aprovados.
- Respostas das três decisões essenciais desta etapa.

## Escopo incluído

- Compose do projeto `forge_system` subindo somente o serviço `postgres`.
- Processo do `backend` na máquina local.
- Tabela da investigação.
- Campos: identificador, título e data de criação.
- `POST /investigations`.
- `GET /investigations/{investigation_id}`.
- Testes desses fluxos.

O título vem de quem chama a API. O identificador e a data de criação ficam a cargo do banco, no formato ainda não aprovado.

## Escopo excluído

`frontend`, imagem Docker do `backend`, alteração e exclusão de investigação, listagem, LLM, conexões, cofre, upload, log e publicação no GitHub.

Reabrir a investigação é a consulta pelo identificador. Não há etapa separada de histórico.

## Arquivos previstos

Nenhum existe ainda.

| Arquivo | Responsabilidade |
| --- | --- |
| `docker-compose.yml` | Sobe somente `postgres`. Os dados ficam fora do Git. |
| `.env.example` | Nomes das variáveis, com valores fictícios. |
| `.gitignore` | Deixa `.env` e o ambiente virtual fora do Git. |
| `backend/requirements.txt` | Bibliotecas para rodar a API. |
| `backend/requirements-dev.txt` | Bibliotecas só dos testes. |
| `backend/app/main.py` | Cria a aplicação e publica as rotas. |
| `backend/app/db.py` | Abre a conexão a partir de `DATABASE_URL`. |
| `backend/app/schema.sql` | Cria a tabela se ela ainda não existir. |
| `backend/app/investigations.py` | Valida o título, executa o SQL e expõe as duas rotas. |
| `backend/tests/test_investigations.py` | Cobre os fluxos principais. |

Um único módulo de investigação basta para um recurso. Separar pastas e classes quando um segundo recurso mostrar a necessidade.

## Dependências propostas

Ainda não são uma lista fechada e não estão instaladas.

Para rodar: `fastapi`, `uvicorn`, `psycopg[binary]`. O FastAPI traz o Pydantic.

Para testar: `pytest` e `httpx`.

Ficam de fora nesta etapa: SQLAlchemy, Alembic, pool de conexões, `python-dotenv`, Testcontainers e bibliotecas de GitHub ou LLM.

## Critérios de aceite

- Criar uma investigação devolve identificador, título e data de criação.
- Consultar esse identificador devolve o mesmo registro.
- Consultar o mesmo identificador por outra conexão ainda devolve o registro.
- Título ausente ou vazio é recusado e não grava linha.
- Identificador inexistente recebe resposta de não encontrado.
- Não existe rota de conexão, log, LLM ou GitHub.

## Testes esperados

Cliente HTTP do FastAPI contra um PostgreSQL de teste. Cada teste começa com a tabela vazia.

| Situação | Resultado esperado |
| --- | --- |
| Título válido | Criação e consulta devolvem o mesmo registro. |
| Outra conexão | O registro continua no banco. |
| Título ausente ou vazio | A API recusa e não grava. |
| Identificador inexistente | A API informa que não encontrou. |

## Documentação a atualizar

`README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LEARNING_GUIDE.md` e esta especificação, para descrever o código que passar a existir. O guia de aprendizagem não pode continuar falando de plano como se fosse implementação.

## Riscos

- `DATABASE_URL` contém segredo e não pode aparecer em código, log, teste ou commit.
- SQL concatenado permitiria mudar o comando. A etapa usa parâmetros.
- Sem autenticação, quem alcançar o endereço de escuta usa a API. O endereço ainda não foi escolhido.
- Volume do PostgreSQL dentro da pasta do repositório mistura dado local e Git. Os dados ficam fora do repositório.
- Teste com banco sujo depende de estado anterior. A tabela de teste começa vazia.

## Decisões pendentes

Essenciais, bloqueiam o código:

1. O identificador é um número gerado pelo PostgreSQL ou outro formato?
2. Qual é o tamanho máximo do título?
3. Em qual endereço a API escuta?

Não bloqueiam esta especificação, e também não devem ser escolhidas em silêncio na implementação: nome do banco e nome do usuário. Se continuarem abertos no momento da autorização, pare e pergunte.

## Aprovação

Depende da etapa 00, já concluída, e da autorização explícita depois que as três decisões essenciais forem respondidas.

## Commits previstos

1. Atualizar os documentos com as respostas das pendências, se ainda não estiverem neles.
2. Adicionar o Compose do `postgres`, o exemplo de ambiente e o `.gitignore`.
3. Adicionar a tabela, as rotas, a validação e os testes.
