# Inspeção do repositório forge (FRG-32)

Fase 0 — Análise. Estudo sem implementação. Nenhum arquivo do repositório foi alterado além deste relatório.

## 1. Identificação da análise

| Item | Valor |
| --- | --- |
| Data da análise | 2026-11-06 (UTC). Revisão 2 no mesmo dia, depois de o responsável informar que o código existente é legado de outro projeto. |
| Repositório | `danielxdrj/forge` (GitHub, visibilidade pública, branch padrão `main`) |
| Commit analisado | `afe7ecd6a8c135e7efefb5b784b852906ab6f66d` (`afe7ecd`), 2026-10-18 03:19:00 -0300, "Feat/empty application shell (#9)" |
| Tag do commit analisado | `v0.9.0` |
| Execução | Agente de IA sem interação humana, em VM Linux (Python 3.12.3, Node 22.23.4, npm 10.9.9, PostgreSQL 16 instalado só para o teste) |

Convenção deste relatório: **[Fato]** foi verificado em arquivo, comando ou commit citado. **[Inferência]** é interpretação minha e precisa de confirmação. **[Informado]** veio do responsável pelo projeto e não pode ser verificado no repositório.

### Contexto informado depois da primeira versão (revisão 2)

**[Informado]** O código que existe hoje no repositório `forge` pertence a **outra ideia de projeto**, não ao Forge atual (ferramenta interna de agentes). Este relatório trata esse conteúdo como **legado de um projeto anterior**. Os fatos levantados (o que existe, se roda, riscos) continuam válidos como descrição do legado. O que mudou foi a leitura: o legado **não representa a direção do Forge** e não deve ser usado para inferir a arquitetura, a stack nem o escopo do Forge atual. A avaliação de reaproveitamento está na seção 10.

## 2. Resumo executivo

> **O código atual é legado de outro projeto e não representa a direção do Forge.** [Informado] Tudo o que o repositório contém hoje descreve esse projeto anterior (um "copiloto local de investigação técnica", de uso individual). O Forge atual é uma ferramenta interna de agentes. O repositório ainda **não contém nada do Forge atual**.

- **[Fato]** O repositório contém, como legado, um backend Python (FastAPI + PostgreSQL) com 3 rotas e 14 testes, e um frontend React estático que não chama o backend. Não há CI, Dockerfile do backend, agentes, orquestração, filas, integração com IA, GitHub, GHCR, Portainer ou n8n.
- **[Fato]** O legado funciona: os 14 testes passam (14 passed) com um PostgreSQL local, o backend sobe e responde, e o frontend compila com `npm ci && npm run build`. Esse funcionamento mostra o estado do legado e não valida nada do Forge atual.
- **[Fato]** Não há segredo versionado (nenhum valor encontrado no working tree nem no histórico; só placeholders em `.env.example`).
- **[Inferência]** Para o Forge atual, o legado tem pouco a oferecer em código. O que pode ter valor está em convenções e processo: regras de segurança de `AGENTS.md`, o protocolo de execução em `.specs/`, o padrão de commits e PRs, os `.gitignore`. Infra e CI praticamente não existem para reaproveitar (um Compose e um Dockerfile de frontend). A avaliação por item está na seção 10.
- **[Fato]** Todo o histórico (10 commits, tags `v0.1.0` a `v0.9.0`, releases e 9 PRs) pertence ao projeto anterior. **[Inferência]** Isso afeta versionamento (a numeração do Forge atual deveria continuar de `0.9.0`?) e o destino do código (seção 13).
- **[Fato]** O repositório está em conta pessoal (`danielxdrj`), é público, e o único autor do histórico é uma pessoa (duas identidades de e-mail). Isso é relevante para o princípio de continuidade e de controle institucional.
- **Destino do legado:** não foi executado nada. As alternativas (branch ou tag de arquivo, pasta `legacy/`, remoção futura) e a recomendação provisória estão na seção 13. A decisão pende do responsável.

## 3. Como repetir a inspeção

Comandos usados (todos de leitura, exceto a criação de um venv e de um banco descartáveis fora do repositório):

```bash
git status; git log --format='%h %ad %an %s' --date=iso; git branch -a; git tag
git for-each-ref --format='%(refname:short) %(objectname:short) %(creatordate:short)' refs/tags
git ls-files
gh repo view --json nameWithOwner,visibility,defaultBranchRef,pushedAt
gh pr list --state all --limit 20
gh api repos/:owner/:repo/actions/workflows

# busca de segredos (somente nomes de arquivo, nunca valores)
rg -n -i "token|secret|password|passwd|api[_-]?key|BEGIN .*PRIVATE|ghp_|sk-" --glob '!frontend/package-lock.json' -l
git log --all --diff-filter=A --name-only --format= | sort -u | rg -i "env|key|pem|secret|credential"

# backend (venv fora do repo)
python3 -m venv /tmp/forge-venv
/tmp/forge-venv/bin/pip install -r backend/requirements-dev.txt
DATABASE_URL='postgresql://forge:<SENHA-FICTICIA>@127.0.0.1:5432/forge' \
  /tmp/forge-venv/bin/python -m pytest -p no:cacheprovider -v     # em backend/
FORGE_HOST=127.0.0.1 FORGE_PORT=8765 /tmp/forge-venv/bin/python -c "from app.main import run; run()"
/tmp/forge-venv/bin/pip-audit -r backend/requirements.txt

# frontend (cópia fora do repo)
cp -r frontend /tmp/fe && cd /tmp/fe && npm ci && npm run build && npm audit && npm outdated
```

O PostgreSQL usado nos testes foi o pacote `postgresql` do Ubuntu (16), com um usuário e uma senha fictícios criados só para esta execução, porque a VM não tem Docker.

## 4. Histórico git

> Legado: **[Informado]** todo este histórico pertence ao projeto anterior, não ao Forge atual.

**[Fato]** (`git log`, `git tag`, `gh pr list`)

- 10 commits em 3 dias: 1 em 2026-10-16, 8 em 2026-10-17, 1 em 2026-10-18. Nenhum commit depois de 2026-10-18.
- Autoria: 1 pessoa (nome "Carlos Daniel"), com dois e-mails diferentes (1 commit com um, 9 com outro).
- Tags `v0.1.0` a `v0.9.0`, uma por PR mergeado (`v0.1.0`=`3d63af3` … `v0.9.0`=`afe7ecd`).
- 9 PRs, todos mergeados (#1 a #9). Branches remotas ainda existentes: `docs/analysis-approval-flow`, `docs/compose-services`, `docs/initial-foundation`, `docs/operational-specs`, `docs/stage-1-decisions`, `feat/01-create-and-read-investigation`, `feat/02-local-log-evidence`, `feat/dark-investigation-screen`, `feat/empty-application-shell`.
- Linha do tempo resumida:
  - `5724f0a` Initial commit
  - `3d63af3` documentos iniciais (#1)
  - `dc8194d` decisões da primeira implementação (#2)
  - `19c39d5` serviços Compose (#3)
  - `0d3ecdd` specs operacionais (#4)
  - `d129986` criar e ler investigação (#5)
  - `1c52eb9` evidência de log local
  - `1992672` tela escura de investigação
  - `550cb4b` fluxo de análise aprovado, só documentação (#8)
  - `afe7ecd` shell da aplicação (#9)
- Padrão de mensagens: majoritariamente Conventional Commits (`docs:`, `feat:`), mas há variações (`fix (docs): ...`, `Feat/empty application shell (#9)`). **[Inferência]** o padrão não é imposto por ferramenta (não há commitlint nem CI).

## 5. Estrutura de pastas e responsabilidades

> Legado: a estrutura abaixo descreve o projeto anterior. Não é a estrutura do Forge atual.

**[Fato]** (`git ls-files`; 57 arquivos versionados, cerca de 4,4 mil linhas)

| Caminho | Responsabilidade aparente |
| --- | --- |
| `README.md`, `AGENTS.md` | Porta de entrada e regras para quem (ou qual agente) altera o repositório. |
| `docs/` (`PRODUCT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `LEARNING_GUIDE.md`, `IMPLEMENTATION_PLAN.md`) | Produto, arquitetura (com hipóteses marcadas), roadmap, guia de aprendizagem, atalho para o plano. |
| `.specs/` (`PROJECT_CONTEXT.md`, `IMPLEMENTATION_PLAN.md`, `EXECUTION_PROTOCOL.md`, `steps/01..08`) | Especificação operacional por etapa; protocolo de execução. |
| `backend/app/main.py` | Cria o app FastAPI; no startup executa `schema.sql`; `run()` lê `FORGE_HOST`/`FORGE_PORT` e inicia o Uvicorn. |
| `backend/app/db.py` | Conexão psycopg via `DATABASE_URL`; `init_schema`. |
| `backend/app/investigations.py` | Modelos Pydantic, SQL parametrizado e as 3 rotas. |
| `backend/app/schema.sql` | Tabelas `investigations` e `evidence`. |
| `backend/tests/test_investigations.py` | 14 testes de integração (HTTP + PostgreSQL real). |
| `frontend/src/` | React 19 + Tailwind 4: `App.jsx`, 5 páginas, 11 componentes, `lib/pagination.js`. |
| `frontend/Dockerfile` | Build Node 22 e publicação com nginx 1.27. |
| `docker-compose.yml` | Projeto `forge_system` com `postgres` (16) e `frontend`. |
| `.env.example` | Placeholders das variáveis de ambiente. |

**[Fato]** Não existem: `.github/`, `Dockerfile` do backend, `LICENSE`, `CODEOWNERS`, imagens ou arquivos de diagrama (`git ls-files` sem `.png/.svg/.drawio`). O único diagrama versionado são dois blocos Mermaid em `docs/ARCHITECTURE.md`; nenhum fala em SaaS.

## 6. Inventário de linguagens, frameworks e versões

> Legado: **[Inferência]** estas tecnologias foram escolhidas para o projeto anterior. Não indicam as tecnologias do Forge atual, que continuam não decididas.

**Linguagens [Fato]:** Python (backend, 4 arquivos `.py` + `schema.sql`), JavaScript/JSX (frontend), Markdown (documentação), SQL (schema).

**Backend** (`backend/requirements.txt`, `backend/requirements-dev.txt`):

| Biblioteca | Declarado | Instalado na análise (2026-11-06) |
| --- | --- | --- |
| fastapi | sem versão | 0.162.0 |
| uvicorn | sem versão | 0.54.0 |
| psycopg[binary] | sem versão | 3.3.8 |
| pytest (dev) | sem versão | 9.2.0 |
| httpx (dev) | sem versão | 0.28.1 |
| (transitivas) pydantic / starlette | — | 2.14.3 / 1.10.0 |

**[Fato]** Nenhuma dependência Python tem versão fixada e não há lockfile. A instalação de outro dia pode trazer versões diferentes. O teste emite `StarletteDeprecationWarning` sobre uso de `httpx` com `starlette.testclient`.

**Frontend** (`frontend/package.json`, `frontend/package-lock.json`): versões exatas fixadas e lockfile presente.

| Pacote | Versão fixada | Mais recente (npm outdated) |
| --- | --- | --- |
| react / react-dom | 19.3.1 | não listado como desatualizado |
| vite | 8.3.4 | 8.3.6 |
| @vitejs/plugin-react | 6.1.2 | 6.2.1 |
| tailwindcss / @tailwindcss/vite | 4.3.3 | 4.3.4 |

**Infra** (`docker-compose.yml`, `frontend/Dockerfile`): imagens `postgres:16`, `node:22-alpine`, `nginx:1.27-alpine`.

**Versão de Python:** não declarada em nenhum arquivo do repositório (sem `pyproject.toml`, `.python-version` ou Dockerfile do backend). Foi testado em 3.12.3.

## 7. Como executar e testar hoje

> Legado: o resultado abaixo descreve o projeto anterior. Serve de registro e de prova de que o legado é executável, não do estado do Forge atual.

A documentação existente é `README.md` (seção "Execução local"), `docs/LEARNING_GUIDE.md` (seção "Variáveis de ambiente") e `.env.example`.

| Verificação | Resultado | Evidência |
| --- | --- | --- |
| Testes do backend com PostgreSQL local | **OK**: 14 passed em 0,82 s | `python -m pytest -v` em `backend/` |
| Testes sem `DATABASE_URL` | Falham (14 errors, `RuntimeError: Defina DATABASE_URL no ambiente.`) | comportamento esperado de `backend/app/db.py` |
| Subir API sem `FORGE_HOST`/`FORGE_PORT` | Encerra com mensagem e código 1 | `backend/app/main.py` (função `run`) |
| API com `FORGE_HOST`/`FORGE_PORT` | **OK**: `POST /investigations`, `POST .../evidence`, `GET /investigations/{id}` e `/docs` (HTTP 200) | `curl` local |
| Preflight CORS (`OPTIONS /investigations` com `Origin`) | HTTP 405 | `curl`; o backend não configura CORS |
| `npm ci` + `npm run build` | **OK**: 34 módulos, build em 125 ms | `frontend/` copiado para `/tmp/fe` |
| `npm audit` / `pip-audit` | 0 vulnerabilidades conhecidas em ambos | executados em 2026-11-06 |
| `docker compose up` | **Não verificado**: Docker não está instalado na VM | — |
| Testes do frontend / lint / typecheck | **Não existem** | `frontend/package.json` só tem `dev`, `build`, `preview` |

Observações:

- **[Fato]** O Python não carrega `.env` sozinho (`docs/LEARNING_GUIDE.md`, seção "Variáveis de ambiente"). Quem roda o backend precisa exportar as variáveis.
- **[Fato]** Os testes usam o banco apontado por `DATABASE_URL` e executam `TRUNCATE investigations RESTART IDENTITY CASCADE` a cada teste (`backend/tests/test_investigations.py`, linha 13). Não existe banco separado para teste. **[Inferência]** rodar a suíte contra um banco com dados reais apaga esses dados.
- **[Fato]** `docker-compose.yml` usa `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, `${POSTGRES_DB}` sem valor padrão; dependem do `.env` local (ausente no repositório, como deve ser). Como o Docker não estava disponível, o comportamento com variáveis vazias não foi testado.

## 8. Estado de funcionamento (do legado)

**Funciona [Fato]:**

- Criar investigação (título 1–200 caracteres, espaços nas pontas removidos; vazio retorna 422).
- Ler investigação por id com suas evidências (404 se não existir).
- Anexar texto de log local como evidência (`origin = "local_log"`; vazio retorna 422; 404 se a investigação não existe).
- Persistência em PostgreSQL com SQL parametrizado (`backend/app/investigations.py`); testes mostram que texto com SQL é gravado como texto.
- Frontend estático compila e navega entre 5 seções.

**Incompleto ou ausente [Fato]:**

- Frontend não faz nenhuma chamada HTTP (`rg "fetch|axios|http" frontend/src` sem resultado de chamada). O texto da própria tela de Conexões diz que o cadastro "ainda depende da integração com o backend" (`frontend/src/pages/ConnectionsPage.jsx`).
- Sem listagem, alteração ou exclusão de investigação (previsto como fora de escopo em `docs/ROADMAP.md`, Etapa 01).
- Sem tabela ou rota de conexões, cofre de segredos, análise por LLM, conectores (todas as etapas 03 a 08 estão "bloqueadas" em `.specs/IMPLEMENTATION_PLAN.md`).
- Sem autenticação: **[Fato]** nenhuma rota exige credencial. O escopo documentado é uso individual e local (`.specs/PROJECT_CONTEXT.md`, "Usuário e ambiente").
- Sem migrações de banco: **[Fato]** o schema é aplicado com `CREATE TABLE IF NOT EXISTS` a cada startup (`backend/app/main.py`, `lifespan`). **[Inferência]** mudanças futuras de schema não têm mecanismo de versionamento.

**Código morto [Fato]:** (dentro do legado) não encontrei. Todos os componentes e `lib/pagination.js` do frontend são importados por algum outro arquivo. As telas usam listas vazias fixas (por exemplo `const connections = [];` em `ConnectionsPage.jsx`), o que é placeholder documentado, não código morto.

**Documentação desatualizada [Fato]:**

- `README.md`, linha 5: "Nesta fase o repositório contém somente documentação. Não há aplicação executável..." contradiz o próprio README ("Estado atual") e o código existente.
- `docs/ARCHITECTURE.md`, linha 122: "Nenhum desses componentes existe no repositório" (seção "Primeira etapa, ainda sem código") contradiz `backend/`.
- `docs/ARCHITECTURE.md`, linha 15 ("o Compose sobe somente o `postgres`") diverge de `docker-compose.yml`, que também sobe o `frontend`; o `README.md` já diz que sobe `postgres` e `frontend`.
- `docs/IMPLEMENTATION_PLAN.md` menciona só a etapa 01 como concluída; `.specs/IMPLEMENTATION_PLAN.md` diz que 01 e 02 estão concluídas.

## 9. Itens relacionados a agentes, orquestração, filas, persistência, interface, GitHub, GHCR, Portainer, IA e n8n

**[Fato]** O Forge atual é uma ferramenta de agentes. Nenhum dos itens de agentes, orquestração, filas ou IA existe no repositório. Isso é coerente com a informação de que o código atual é de outro projeto.

| Tema | Existe em código/infra? | Evidência |
| --- | --- | --- |
| Agentes / orquestração | **Não.** Só aparece como rótulo vazio na aba "Agentes" da tela "Automações & LLMs". | `frontend/src/pages/AutomationsPage.jsx` (linhas 10, 17, 28) |
| Filas / workers | **Não.** | `rg "celery|redis|queue|fila"` em `*.py/*.js/*.jsx/*.yml` sem resultado |
| Persistência | **Sim.** PostgreSQL 16, tabelas `investigations` e `evidence`. | `backend/app/schema.sql`, `docker-compose.yml` |
| Interface | **Sim, parcial.** React estático sem chamada à API; docs interativas do FastAPI em `/docs`. | `frontend/`, teste manual com `curl` |
| Provedores de IA / LLM | **Não.** Só em texto e rótulos. | `rg "openai|anthropic|llm"` em código sem resultado funcional |
| GitHub (integração) | **Não.** Só documentação (Etapas 06 e 07 bloqueadas). O repositório em si está no GitHub. | `docs/ROADMAP.md`, `.specs/steps/07-github-task-creation.md` |
| GitHub Actions / CI | **Não.** Sem `.github/`; API do GitHub retorna 0 workflows. | `ls .github`, `gh api repos/:owner/:repo/actions/workflows` (`total_count: 0`) |
| GHCR / imagens publicadas | **Não.** Nenhuma referência a `ghcr.io`; o `docker-compose.yml` constrói o frontend localmente (`build: ./frontend`). | `docker-compose.yml` |
| Portainer | **Só rótulo.** Opção de tipo de conexão na tela e item de roadmap. | `frontend/src/pages/ConnectionsPage.jsx`, `docs/ROADMAP.md` (Etapa 06) |
| n8n | **Nenhuma menção** em todo o repositório. | `rg -i n8n` sem resultado |

## 10. Avaliação do legado: reaproveitar, adaptar, descartar ou arquivar

Premissa **[Informado]**: o código é de outro projeto e não representa o Forge atual. A classificação abaixo é **[Inferência]** minha, com base no que foi verificado nas seções 5 a 9, e depende da decisão do responsável sobre o destino do legado (seção 13). Nenhuma ação foi executada.

Legenda: **Reaproveitar** (útil quase como está), **Adaptar** (a ideia serve, o conteúdo muda), **Arquivar** (guardar para consulta, fora da árvore principal), **Descartar** (sem valor para o Forge atual; só depois de aprovação).

### 10.1 Infraestrutura, CI e Docker

| Item | Caminho | Classificação | Justificativa |
| --- | --- | --- | --- |
| Compose do PostgreSQL e do frontend | `docker-compose.yml` | **Descartar / arquivar** | **[Fato]** Sobe `postgres:16` e um frontend do projeto anterior. **[Inferência]** O Forge atual tem banco, linguagem e serviços não decididos; um Compose pronto induziria uma decisão. O padrão de usar `127.0.0.1` nas portas publicadas (**[Fato]**) pode ser lembrado como convenção. |
| Dockerfile do frontend (build Node e nginx) | `frontend/Dockerfile`, `frontend/.dockerignore` | **Arquivar** | **[Fato]** Específico do frontend legado. O padrão de multi-stage build é genérico, mas não reaproveitável sem a tela. |
| CI de testes, GitHub Actions, GHCR, Portainer | — | **Nada a reaproveitar** | **[Fato]** Não existem no repositório. O CI e o deploy citados no planejamento precisam ser levantados em outro lugar (pergunta 4). |
| Automação de release (PR #11, proposta, ainda não mergeada) | `.github/workflows/release.yml` e arquivos relacionados, na branch `ci/release-automation` | **Reaproveitar (independente do legado)** | **[Fato]** Foi criada em tarefa separada e não depende do código legado. A versão inicial do manifesto (`0.9.0`) vem das tags do legado; ver pergunta 7. |

### 10.2 Convenções e processo

| Item | Caminho | Classificação | Justificativa |
| --- | --- | --- | --- |
| Regras de agentes (leitura somente, segredo fora do Git, parar e perguntar, definição de pronto) | `AGENTS.md` | **Adaptar** | **[Fato]** O texto está acoplado ao projeto anterior (investigação, conectores, etapas). **[Inferência]** Os princípios (segredos fora do Git, placeholders, testes com dados fictícios, não escolher em silêncio decisão pendente) conversam com os requisitos do Forge atual, mas o escopo e a regra "integrações somente leitura" precisam ser revistos. Pergunta 9. |
| Protocolo de execução por etapa e specs | `.specs/EXECUTION_PROTOCOL.md`, `.specs/steps/` | **Adaptar (protocolo) / arquivar (specs)** | **[Inferência]** O protocolo é um modelo de como conduzir tarefas pequenas e verificáveis. As specs `01` a `08` descrevem o projeto anterior. |
| Documentos de produto, arquitetura, roadmap e guia | `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LEARNING_GUIDE.md`, `docs/IMPLEMENTATION_PLAN.md`, `README.md` | **Arquivar** | **[Fato]** Descrevem o copiloto de investigação. **[Inferência]** Mantidos como estão, induzem a erro quem chegar ao repositório. Precisam de aviso de legado ou de substituição (seção 13). |
| Conventional Commits, PRs, tags semver | histórico git | **Reaproveitar** | **[Fato]** Mensagens majoritariamente em Conventional Commits, um PR por etapa e uma tag por PR. É a convenção que a automação de release formaliza. |
| `.gitignore` (`.env`, `.venv/`, `node_modules/`, `dist/`) | `.gitignore` | **Adaptar** | **[Fato]** Cobre o stack do legado. **[Inferência]** Revisar para o stack final e acrescentar padrões de segredo (`.env.*`, `*.pem`, `*.key`). |
| `.env.example` com placeholders | `.env.example` | **Adaptar (padrão)** | **[Fato]** Usa placeholders óbvios (`<SENHA>`). O padrão é bom; as variáveis são do legado. |

### 10.3 Código e utilitários

| Item | Caminho | Classificação | Justificativa |
| --- | --- | --- | --- |
| API de investigações (rotas, validação, SQL) | `backend/app/investigations.py`, `backend/app/main.py`, `backend/app/db.py`, `backend/app/schema.sql` | **Arquivar** | **[Fato]** Específico de "investigação" e "evidência". **[Inferência]** Sem relação com agentes. Pode servir de consulta de estilo (SQL parametrizado, validação com Pydantic) se o Forge adotar Python, o que não está decidido. |
| Testes de integração | `backend/tests/test_investigations.py` | **Arquivar** | **[Fato]** Testam só o domínio do legado e usam `TRUNCATE` no banco apontado. |
| Frontend (shell, componentes, páginas) | `frontend/src/` | **Arquivar** | **[Fato]** Tela do copiloto de investigação, sem chamada à API. **[Inferência]** Componentes genéricos (`Button`, `Modal`, `Tabs`, `Pagination`, `lib/pagination.js`) são reaproveitáveis se o Forge tiver interface web, o que não está definido. |
| Dependências e lockfile do frontend | `frontend/package.json`, `frontend/package-lock.json` | **Descartar com o frontend** | **[Fato]** Sem vulnerabilidades conhecidas em 2026-11-06 (seção 11.2), mas só têm sentido com a tela. |
| Dependências Python | `backend/requirements*.txt` | **Descartar com o backend** | **[Fato]** Sem versão fixada. Só têm sentido com o backend legado. |

### 10.4 Síntese

- **[Inferência]** O que tem valor para o Forge atual é pouco e está em processo e convenções: princípios de segurança, protocolo de execução, Conventional Commits, tags semver e placeholders de configuração.
- **[Inferência]** O código funcional (backend e frontend) e a infraestrutura Docker pertencem ao projeto anterior. Não há agentes, filas ou integrações para reaproveitar.
- **[Inferência]** Antes de FRG-9 (tecnologias reaproveitáveis) é preciso confirmar se qualquer coisa deste repositório deve influenciar o Forge atual. Minha leitura é que não deve influenciar a escolha de tecnologia.

## 11. Riscos do legado

### 11.1 Segredos (sem valores)

**[Fato]** Nenhum valor de segredo encontrado no working tree nem no histórico:

- Arquivos com termos como "senha", "token", "secret" são documentação e código que apenas descrevem a regra: `README.md`, `AGENTS.md`, `docker-compose.yml` (referência `${POSTGRES_PASSWORD}`), `docs/ARCHITECTURE.md`, `docs/LEARNING_GUIDE.md`, `docs/ROADMAP.md`, `frontend/src/pages/ConnectionsPage.jsx` (rótulo do campo "referência do segredo").
- Único arquivo de configuração adicionado ao histórico: `.env.example`, só com placeholders (`<SENHA>`, `<HOST>`, `<PORT>`) e os nomes `forge` para usuário e banco.
- `.gitignore` cobre `.env`, `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `node_modules/`, `dist/`.

**Riscos relacionados [Inferência]:**

- `.gitignore` não cobre outros arquivos de segredo que o `AGENTS.md` prevê ("qualquer arquivo de segredo"), como `.env.*` (exceto `.env.example`), `*.pem` ou `*.key`.
- Não há varredura automática de segredos (sem CI, sem pre-commit).
- O repositório é **público** (`gh repo view`: `isPrivate: false`). Qualquer segredo commitado por engano ficaria exposto publicamente.
- A conexão `origin` do clone usado nesta análise tem credencial embutida na URL. Isso é configuração do ambiente da VM, não está versionado. Registrei só o fato, sem valor.

### 11.2 Dependências

- **[Fato]** `pip-audit` e `npm audit` sem vulnerabilidades conhecidas em 2026-11-06.
- **[Fato]** Frontend 1 a 2 versões patch/minor atrás (seção 6); sem sinal de abandono.
- **[Fato]** Dependências Python sem versão fixada e sem lockfile. **[Inferência]** build não reprodutível e risco de quebra por atualização de versão maior.
- **[Fato]** Versões muito recentes de várias bibliotecas (por exemplo React 19.3, Vite 8, Pydantic 2.14); não avaliei maturidade nem compatibilidade de longo prazo.

### 11.3 Testes

- **[Fato]** Backend: 14 testes de integração, cobrindo as 3 rotas e os principais erros. Não há testes unitários isolados, de configuração (`run()`), nem de `schema.sql` em banco já existente.
- **[Fato]** Frontend: nenhum teste, lint ou typecheck.
- **[Fato]** Nenhuma execução automática de testes (sem CI). **[Inferência]** a única garantia hoje é a execução manual.
- **[Fato]** Os testes dependem de um PostgreSQL disponível e apagam as tabelas (seção 7).

### 11.4 Continuidade e independência operacional

- **[Fato]** Repositório em conta pessoal (`danielxdrj/forge`), um único autor, sem `CODEOWNERS`, sem `LICENSE`. **[Inferência]** conflita com o requisito de que credenciais e recursos fiquem sob controle institucional da empresa; precisa de decisão (seção 13).
- **[Fato]** Existe documentação extensa, protocolo de execução e specs por etapa (`.specs/`, `docs/`). **[Informado]** Descrevem o projeto anterior. **[Inferência]** Para quem herdar o Forge atual, esse material é enganoso se ficar na árvore sem aviso de legado, e parte dele está desatualizada até para o próprio legado (seção 8).
- **[Fato]** Não existe ainda nenhum procedimento manual equivalente documentado para automações, porque não há automações.

### 11.5 Segurança da aplicação (estado atual)

- **[Fato]** API sem autenticação, sem CORS e sem limite de tamanho para o texto do log (`EvidenceCreate.content` só exige `min_length=1`; a pendência está registrada em `docs/ROADMAP.md`, Etapa 02).
- **[Fato]** O Compose publica o PostgreSQL e o frontend só em `127.0.0.1` (`docker-compose.yml`).
- **[Fato]** O endereço de escuta da API não tem padrão: `FORGE_HOST`/`FORGE_PORT` obrigatórios (`backend/app/main.py`). Se alguém definir `0.0.0.0`, a API fica exposta sem autenticação. **[Inferência]** risco só se o operador fizer isso.

## 12. Alternativas para onde guardar este relatório (repositório × Notion)

**Decisão provisória:** esta execução rodou sem interação humana. O relatório foi salvo no repositório. **A escolha pende de confirmação do responsável pelo projeto.**

| Critério | Repositório (`docs/analise/`) | Notion |
| --- | --- | --- |
| Versionamento e revisão | Prós: histórico git, revisão por PR, vinculado ao commit analisado. Contras: nenhum relevante. | Prós: histórico de páginas. Contras: não se vincula a um commit; revisão menos rígida. |
| Continuidade e transferência | Prós: acompanha o código; quem clona o repositório recebe tudo; independe de licença de terceiros. | Prós: bom para navegação e busca por quem não é desenvolvedor. Contras: depende de workspace e permissões, que podem estar em conta pessoal. |
| Segredos | Prós: fácil impor regras (`.gitignore`, varredura). Contras: repositório é público, então o conteúdo fica público. | Contras: o controle de acesso é outro; precisa definir quem vê. |
| Acesso por não desenvolvedores | Contras: exige GitHub. | Prós: acessível a toda a equipe. |
| Alinhamento com `AGENTS.md` | Prós: o próprio `AGENTS.md` pede documento atualizado na mesma alteração. | Contras: duplica fontes e cria risco de duas versões divergentes (regra de `.specs/PROJECT_CONTEXT.md`). |
| Conteúdo sensível | Contras: este relatório cita caminhos de arquivos e riscos em repositório público (sem valores de segredo). | Prós: pode ficar restrito. |

**Recomendação provisória:** manter o relatório no repositório (rastreável ao commit, transferível, na mesma revisão do código) e, se a equipe precisar de leitura mais ampla, publicar no Notion apenas um resumo com link para o arquivo. Se o responsável preferir não expor riscos em repositório público, mover o arquivo para o Notion restrito ou para um repositório privado. **Decisão para aprovação do responsável.**

## 13. Destino do código legado (alternativas, sem executar nada)

Esta análise **não moveu, removeu nem arquivou nada**. As alternativas abaixo são para decisão do responsável, em tarefa futura. Todas mantêm o histórico git, porque ele é a única cópia do legado além da conta do GitHub.

| Alternativa | Como seria | Prós | Contras |
| --- | --- | --- | --- |
| A. Tag e branch de arquivo, depois remover da `main` | Criar uma tag (por exemplo `legacy/v0.9.0`, sobre `afe7ecd`) e uma branch de arquivo; em PR próprio, remover o código da `main`. | Árvore limpa para o Forge atual. Legado recuperável por tag e branch. Sem pastas mortas na `main`. | A tag e a branch precisam ser protegidas e documentadas. Quem só olha a `main` não vê o legado. As tags existentes (`v0.1.0` a `v0.9.0`) e a numeração de release continuam apontando para o legado (pergunta 7). |
| B. Pasta `legacy/` na `main` | Mover `backend/`, `frontend/`, `docker-compose.yml` e os documentos para `legacy/`, com um `README` de aviso. | Fácil de consultar. Nenhuma operação irreversível. | Mantém código morto na árvore, no CI e em varreduras. Risco de ser confundido com o Forge atual e de ser evoluído por engano. Dependências desatualizadas continuam no repositório. |
| C. Novo repositório para o legado | Copiar o legado, com histórico, para outro repositório arquivado (de preferência na organização da empresa). Limpar o `forge`. | Separa projetos de forma explícita. O repositório `forge` fica só com o Forge atual. | Exige criar repositório, permissões e copiar PRs/issues, que não migram sozinhos. Mais passos. |
| D. Remover sem arquivo separado | Apagar o código da `main`, confiando no histórico git. | Mais simples. | O legado só se acha pelo histórico, sem marco claro. Mais difícil de explicar para quem chegar depois. |
| E. Deixar como está | Só marcar `README.md` com aviso de legado. | Sem esforço. | O repositório continua enganoso e mistura os dois projetos. |

**Recomendação provisória [Inferência]:** alternativa A, ou C se a empresa quiser separar de vez os projetos e a conta pessoal. Em ambos os casos, criar o marco do legado (tag/branch ou repositório) **antes** de remover qualquer coisa, e só então remover o código da `main` numa tarefa própria, com aprovação explícita. Enquanto isso não ocorre, um aviso de legado no `README.md` evita confusão. **Decisão para aprovação do responsável.**

## 14. Recomendação, decisões para aprovação e próximos passos

Recomendação justificada (limitada ao escopo de análise; nada disso foi implementado):

1. Tratar este levantamento como entrada de FRG-23, FRG-9 e FRG-25, **com o código existente como legado**. **[Inferência]** FRG-23 (documentar a arquitetura atual) deve descrever que o Forge atual ainda não tem código no repositório, e registrar o legado só como histórico. FRG-9 deve partir de processo e convenções (seção 10), não do código.
2. Não escolher linguagem, banco ou arquitetura final com base neste repositório. **[Fato]** Python, FastAPI, PostgreSQL e React foram escolhas do projeto anterior. **[Inferência]** Para o Forge atual, elas continuam decisões pendentes.
3. Resolver o destino do legado (seção 13) antes de começar a escrever o Forge atual no mesmo repositório, para não misturar os dois projetos na mesma árvore, no CI e nas releases.
4. Decidir se o Forge atual continua neste repositório (com o histórico do legado) ou ganha um repositório novo, sob controle institucional.

**Decisões para aprovação do responsável:**

- Destino do código legado (seção 13).
- Onde manter este relatório (seção 12).
- Se o repositório deve continuar público e na conta pessoal.
- Se a numeração de versão do Forge atual continua de `0.9.0` ou recomeça.

**Riscos:**

- Misturar legado e Forge atual na mesma árvore, induzindo decisões a partir do que existe (viés de stack).
- Remover o legado sem marco de arquivo: perda de consulta.
- A automação de release proposta no PR #11 (ainda não mergeada) parte de `0.9.0`, versão do legado.
- Repositório público em conta pessoal: risco de continuidade e de exposição.

## 15. Perguntas em aberto

1. **Destino do código legado:** qual alternativa da seção 13 (A tag e branch de arquivo, B pasta `legacy/`, C novo repositório, D remover, E manter com aviso)? Em qual tarefa isso será feito, e quem aprova?
2. **Documentação do legado:** `AGENTS.md`, `.specs/` e `docs/` também pertencem ao projeto anterior, ou só o código? Se forem do legado, o protocolo de execução e as regras de segurança valem para o Forge atual?
3. **Repositório do Forge atual:** o Forge atual será desenvolvido neste repositório (`danielxdrj/forge`) ou em um novo, numa organização da Ferreira & Borzone? O repositório deve ser privado?
4. **GitHub Actions, GHCR e Portainer:** onde estão hoje o CI e o deploy mencionados no planejamento? Pertencem a outros repositórios? O Forge atual será publicado como imagem?
5. **n8n:** há alguma instância ou fluxo existente que deva ser considerado em FRG-9? O repositório não tem nenhuma referência.
6. **Diagrama de arquitetura com a visão ampla (inclusive SaaS):** onde está? Não está no repositório (só os 2 blocos Mermaid em `docs/ARCHITECTURE.md`, do projeto anterior, sem SaaS). Preciso de acesso somente leitura para as próximas tarefas.
7. **Versionamento:** as tags e releases `v0.1.0` a `v0.9.0` são do legado. O Forge atual deve continuar a numeração (a automação de release do PR #11 parte de `0.9.0`) ou recomeçar, por exemplo em `0.1.0` num repositório novo?
8. **Autoria e contas:** os dois e-mails do histórico (`Carlos Daniel`) são da mesma pessoa? Algum é de conta pessoal que deva ser substituído por conta institucional?
9. **Regras de `AGENTS.md`:** a regra "integrações externas são somente leitura" e a divisão em etapas valem para o Forge atual, ou eram específicas do projeto anterior?
10. **Docker/Compose:** o `docker compose up` do legado foi executado com o `.env` real? (Não pude verificar; Docker ausente na VM.) Só importa se o legado for mantido.
11. **Licença:** o repositório, se continuar público, deve ter licença? Hoje não há `LICENSE`.
12. **Material externo:** o enunciado cita "documentação já produzida pelas tarefas anteriores", mas esta é a primeira tarefa (sem dependências). Existe material fora do repositório (Notion, Drive etc.) que deva ser considerado, em especial sobre o Forge atual?
13. **Local do relatório:** repositório ou Notion (seção 12)?

## 16. Limitações desta análise

- A afirmação de que o código existente é de outro projeto é **[Informado]**; não consigo confirmá-la no repositório. Os documentos do repositório (`README.md`, `AGENTS.md`, `.specs/`) tratam esse código como o próprio Forge. Não tenho acesso ao diagrama nem ao planejamento do Forge atual, então a avaliação de reaproveitamento (seção 10) é uma inferência.
- Docker não estava disponível: `docker-compose.yml` e `frontend/Dockerfile` foram lidos, não executados. O build do frontend foi feito com `npm` direto.
- Os testes foram executados com um PostgreSQL 16 do pacote Ubuntu, não com a imagem `postgres:16` do Compose.
- Não avaliei qualidade de design visual do frontend nem desempenho.
- A leitura de `.specs/steps/03..08` foi parcial (confirmei estado "bloqueada" e as pendências citadas no roadmap). Não fiz auditoria linha a linha desses arquivos.
- Não consultei fontes externas (documentação oficial) porque nada na análise exigiu uma afirmação sobre comportamento de produto de terceiros. As versões "mais recentes" vêm de `npm outdated` e `pip` em 2026-11-06.
