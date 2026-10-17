# Guia de aprendizagem

Este guia descreve o código da etapa que cria e consulta uma investigação. O plano das etapas seguintes está em [../.specs/IMPLEMENTATION_PLAN.md](../.specs/IMPLEMENTATION_PLAN.md).

## HTTP

`POST /investigations` cria o registro e responde `201`. `GET /investigations/{investigation_id}` devolve o mesmo registro, ou `404` quando o identificador não existe. Título ausente, vazio ou só com espaços responde `422`.

`POST /investigations/{investigation_id}/evidence` anexa o texto de um log local. A consulta da investigação devolve essa evidência, com origem `local_log`. A API não lê arquivo do disco e não recebe credencial.

## API

As duas rotas estão em `backend/app/investigations.py`. A documentação interativa do FastAPI continua sendo o uso da API. A pasta `frontend` é uma aplicação React com Tailwind. Ela mostra a tela escura e ainda não chama essas rotas.

## FastAPI

`backend/app/main.py` cria a aplicação e, ao iniciar, executa `backend/app/schema.sql`. O servidor é o Uvicorn. Ele só sobe se `FORGE_HOST` e `FORGE_PORT` estiverem no ambiente. Não há endereço padrão.

## Validação

`InvestigationCreate` limita o título a 200 caracteres e remove espaços nas pontas antes de medir. O título limpo entra no banco. Um título vazio não chega ao `INSERT`.

## PostgreSQL

O serviço `postgres` do Compose guarda os dados do Forge. O banco e o usuário se chamam `forge`. A senha fica em `POSTGRES_PASSWORD` e em `DATABASE_URL`. O arquivo `.env` está fora do Git. O exemplo versionado é `.env.example`, com `<SENHA>`.

Na primeira execução, só o `postgres` sobe pelo Compose. O backend roda na máquina. A `DATABASE_URL` usa `127.0.0.1`, porque a porta publicada do banco é `127.0.0.1:5432`. Isso não é o endereço da API.

## SQL parametrizado

`create_investigation` e `get_investigation` enviam o título e o identificador como parâmetros `%s`. O texto do título não é concatenado ao comando.

A coluna `id` é `bigint GENERATED ALWAYS AS IDENTITY`. `created_at` recebe o horário do banco.

## Testes automatizados

`backend/tests/test_investigations.py` usa o cliente HTTP do FastAPI e um PostgreSQL de teste. Cada teste esvazia a tabela `investigations`.

O teste que abre outra conexão mostra que o registro continua no banco depois que a conexão da criação fecha.

## Variáveis de ambiente

| Variável | Uso |
| --- | --- |
| `POSTGRES_USER` | Usuário do banco. O valor aprovado é `forge`. |
| `POSTGRES_PASSWORD` | Senha. Fica vazia até ser preenchida. |
| `POSTGRES_DB` | Nome do banco. O valor aprovado é `forge`. |
| `DATABASE_URL` | Endereço que a API usa para conectar. |
| `FORGE_HOST` | Endereço em que a API escuta. Sem valor padrão. |
| `FORGE_PORT` | Porta em que a API escuta. Sem valor padrão. |

O Python não carrega o `.env` sozinho. O Compose lê esse arquivo para subir o `postgres`. Para rodar a API, as variáveis precisam estar no ambiente do processo.

## O que este guia não cobre ainda

LLM, upload de log, conectores externos, cofre de segredos, a ligação da tela com a API e a publicação de tarefas no GitHub continuam nas etapas seguintes.
