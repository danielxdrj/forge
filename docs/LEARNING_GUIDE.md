# Guia de aprendizagem

Este guia descreve o código da etapa que cria e consulta uma investigação. O plano das etapas seguintes está em [../.specs/IMPLEMENTATION_PLAN.md](../.specs/IMPLEMENTATION_PLAN.md).

## HTTP

`POST /investigations` cria o registro e responde `201`. `GET /investigations/{investigation_id}` devolve o mesmo registro, ou `404` quando o identificador não existe. Título ausente, vazio ou só com espaços responde `422`.

`POST /investigations/{investigation_id}/evidence` anexa o texto de um log local. A consulta da investigação devolve essa evidência, com origem `local_log`. A API não lê arquivo do disco e não recebe credencial.

## API

As rotas de investigação e de evidência estão em `backend/app/investigations.py`. A documentação interativa do FastAPI continua sendo o uso da API.

## FastAPI

`backend/app/main.py` cria a aplicação e, ao iniciar, executa `backend/app/schema.sql`. O servidor é o Uvicorn. Ele só sobe se `FORGE_HOST` e `FORGE_PORT` estiverem no ambiente. Não há endereço padrão.

## Validação

`InvestigationCreate` limita o título a 200 caracteres e remove espaços nas pontas antes de medir. O título limpo entra no banco. Um título vazio não chega ao `INSERT`.

## PostgreSQL

O serviço `postgres` do Compose guarda os dados do Forge. O banco e o usuário se chamam `forge`. A senha fica em `POSTGRES_PASSWORD` e em `DATABASE_URL`. O arquivo `.env` está fora do Git. O exemplo versionado é `.env.example`, com `<SENHA>`.

O Compose sobe `postgres` e `frontend`. O backend roda na máquina. A `DATABASE_URL` usa `127.0.0.1`, porque a porta publicada do banco é `127.0.0.1:5432`. Isso não é o endereço da API.

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

## Tela

A tela fica em `frontend`. JavaScript é a linguagem. React monta o que aparece, Tailwind aplica o tema escuro e o Vite junta isso num build estático.

`frontend/src/App.jsx` escolhe a seção. `frontend/src/components/AppShell.jsx` monta a navegação, a barra e o Canvas. `frontend/src/index.css` declara as cores. `frontend/vite.config.js` liga o React e o Tailwind. O `Dockerfile` executa o build e o nginx publica o resultado.

As seções são investigação, automações, log local, conexões e configurações. As listas começam vazias. O formulário de conexão pede nome, tipo, destino e referência do segredo, e não grava o valor do segredo. Não há chamada à API e não há registros de exemplo.

## Painel local (ADR-017)

O Compose `docker-compose.forge.yml` sobe `forge_postgres`, `forge_backend` (API JSON em FastAPI) e `forge_frontend` (nginx, `127.0.0.1:8090`). A UI é HTML + JS vanilla em `deploy/frontend/html/` (sem `innerHTML` para texto do LLM), com barra lateral: Tarefas, Investigação, Teia de contexto e Conexões. O tema segue a paleta Ferreira & Borzone (vinho `#990000`), com modo claro (`#F7F6F4`) e escuro (`#121212`); a escolha fica em `localStorage` e o padrão segue `prefers-color-scheme`, aplicado por `theme.js` no `<head>` (sem script inline). Fontes Inter e Playfair Display ficam em `deploy/frontend/html/fonts/` (OFL, sem CDN). Investigação lista issues e notas manuais (`/api/notes`, Postgres, sem vault). Teia lê o vault Obsidian se `FORGE_OBSIDIAN_VAULT` e `FORGE_OBSIDIAN_ALLOW` existirem, e mostra o status Graphify (`/api/graphs`, volume `forge_graphs`). A aba Conexões só aparece para o papel owner; a API `/api/connections` continua owner/editor como antes. Login por device flow em `/api/auth/*`; a sessão persiste no Postgres (`token_hash`, prazo 7 dias, renovação deslizante) e, na CLI, num arquivo 0600 no volume `forge_cli_home`. Criar tarefa: `/api/repos`, `/api/tasks/generate`, campos do board, `/api/tasks/{id}/confirm`. A lista separa Publicadas (com `task_links` de issue) e Rascunhos; `POST /api/tasks/{id}/discard` cancela o rascunho (status `cancelado`, sem apagar). Testes em `tests/core/test_web_auth.py` e `tests/core/test_web_tasks.py` usam GitHub/Cursor/gh falsos. Grafos e vault: `tests/core/test_graphs.py`, `tests/core/test_obsidian.py`, `tests/core/test_notes.py`.

A área Conexões (`/conexoes`, API `/api/connections`) cadastra MySQL/Postgres/FTP/SFTP/Portainer com vários hosts. O segredo fica cifrado (Fernet) em `connections.secret_ciphertext`; a chave vem de `/run/secrets/forge_connections_key` (env `FORGE_CONNECTIONS_KEY` → tmpfs no entrypoint). A API só devolve `secret_set`. Testes em `tests/core/test_connections.py` e `tests/core/test_web_connections.py` (rede falsa). Usar a conexão numa investigação ainda não entra.

## Rascunho de issue

`src/forge_core/draft/` lê contexto por `ContextSource` (`--contexto` / `--arquivo`, stdin `-`), gera o corpo no template fixo e só então, com confirmação ou `--retomar`, chama o `gh` (dublê em `tests/core/test_draft.py`). O gerador sempre preenche Comportamento esperado e Critérios de aceite (prefixo `_Sugestão (revise):_` quando infere); só Objetivo pode ficar `[PENDENTE]`, e só com contexto vazio. O painel web chama o mesmo `DraftService`.

## Resolver de issue

`src/forge_core/resolver/` clona o repo-alvo, chama o mesmo `ProviderAdapter.complete` em modo implementador (Cursor CLI hoje) só no clone temporário e, após `s`/`sim`, o Forge faz push e abre PR em rascunho (`Closes #n`). Testes em `tests/core/test_resolver.py` usam motor e `gh` falsos.

## O que este guia não cobre ainda

Upload de log, usar uma conexão na investigação, LLM e agentes privilegiados continuam nas etapas seguintes.
