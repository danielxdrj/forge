# Inspeção do repositório forge (FRG-32)

Fase 0 — Análise. Estudo sem implementação. Nenhum arquivo do repositório foi alterado além deste relatório.

## 1. Identificação da análise

| Item | Valor |
| --- | --- |
| Data da análise | 2026-11-06 (UTC) |
| Repositório | `danielxdrj/forge` (GitHub, visibilidade pública, branch padrão `main`) |
| Commit analisado | `afe7ecd6a8c135e7efefb5b784b852906ab6f66d` (`afe7ecd`), 2026-10-18 03:19:00 -0300, "Feat/empty application shell (#9)" |
| Tag do commit analisado | `v0.9.0` |
| Execução | Agente de IA sem interação humana, em VM Linux (Python 3.12.3, Node 22.23.4, npm 10.9.9, PostgreSQL 16 instalado só para o teste) |

Convenção deste relatório: **[Fato]** foi verificado em arquivo, comando ou commit citado. **[Inferência]** é interpretação minha e precisa de confirmação.

## 2. Resumo executivo

- **[Fato]** O repositório contém um backend Python (FastAPI + PostgreSQL) com 3 rotas e 14 testes, e um frontend React estático que ainda não chama o backend. Não há CI, Dockerfile do backend, agentes, orquestração, filas, integração com IA, GitHub, GHCR, Portainer ou n8n em código.
- **[Fato]** Os 14 testes passam (14 passed) com um PostgreSQL local. O backend sobe e responde a `POST /investigations`, `POST /investigations/{id}/evidence`, `GET /investigations/{id}` e `/docs`. O frontend compila com `npm ci && npm run build`.
- **[Fato]** Não há segredo versionado (nenhum valor de credencial encontrado no working tree nem no histórico; só placeholders em `.env.example`).
- **[Inferência]** A visão descrita no enunciado da tarefa (ferramenta interna que coordena agentes especializados, automações, n8n, GitHub Actions, GHCR, Portainer) **não corresponde** ao que o repositório documenta e implementa hoje (copiloto local de investigação técnica, uso individual, nesta máquina). Essa divergência é a principal pergunta em aberto (seção 13).
- **[Fato]** O repositório está em conta pessoal (`danielxdrj`) e o único autor do histórico é uma pessoa (duas identidades de e-mail). Isso é relevante para o princípio de continuidade e de controle institucional.

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

## 8. Estado de funcionamento

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

**Código morto [Fato]:** não encontrei. Todos os componentes e `lib/pagination.js` do frontend são importados por algum outro arquivo. As telas usam listas vazias fixas (por exemplo `const connections = [];` em `ConnectionsPage.jsx`), o que é placeholder documentado, não código morto.

**Documentação desatualizada [Fato]:**

- `README.md`, linha 5: "Nesta fase o repositório contém somente documentação. Não há aplicação executável..." contradiz o próprio README ("Estado atual") e o código existente.
- `docs/ARCHITECTURE.md`, linha 122: "Nenhum desses componentes existe no repositório" (seção "Primeira etapa, ainda sem código") contradiz `backend/`.
- `docs/ARCHITECTURE.md`, linha 15 ("o Compose sobe somente o `postgres`") diverge de `docker-compose.yml`, que também sobe o `frontend`; o `README.md` já diz que sobe `postgres` e `frontend`.
- `docs/IMPLEMENTATION_PLAN.md` menciona só a etapa 01 como concluída; `.specs/IMPLEMENTATION_PLAN.md` diz que 01 e 02 estão concluídas.

## 9. Itens relacionados a agentes, orquestração, filas, persistência, interface, GitHub, GHCR, Portainer, IA e n8n

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

## 10. Riscos

### 10.1 Segredos (sem valores)

**[Fato]** Nenhum valor de segredo encontrado no working tree nem no histórico:

- Arquivos com termos como "senha", "token", "secret" são documentação e código que apenas descrevem a regra: `README.md`, `AGENTS.md`, `docker-compose.yml` (referência `${POSTGRES_PASSWORD}`), `docs/ARCHITECTURE.md`, `docs/LEARNING_GUIDE.md`, `docs/ROADMAP.md`, `frontend/src/pages/ConnectionsPage.jsx` (rótulo do campo "referência do segredo").
- Único arquivo de configuração adicionado ao histórico: `.env.example`, só com placeholders (`<SENHA>`, `<HOST>`, `<PORT>`) e os nomes `forge` para usuário e banco.
- `.gitignore` cobre `.env`, `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `node_modules/`, `dist/`.

**Riscos relacionados [Inferência]:**

- `.gitignore` não cobre outros arquivos de segredo que o `AGENTS.md` prevê ("qualquer arquivo de segredo"), como `.env.*` (exceto `.env.example`), `*.pem` ou `*.key`.
- Não há varredura automática de segredos (sem CI, sem pre-commit).
- O repositório é **público** (`gh repo view`: `isPrivate: false`). Qualquer segredo commitado por engano ficaria exposto publicamente.
- A conexão `origin` do clone usado nesta análise tem credencial embutida na URL. Isso é configuração do ambiente da VM, não está versionado. Registrei só o fato, sem valor.

### 10.2 Dependências

- **[Fato]** `pip-audit` e `npm audit` sem vulnerabilidades conhecidas em 2026-11-06.
- **[Fato]** Frontend 1 a 2 versões patch/minor atrás (seção 6); sem sinal de abandono.
- **[Fato]** Dependências Python sem versão fixada e sem lockfile. **[Inferência]** build não reprodutível e risco de quebra por atualização de versão maior.
- **[Fato]** Versões muito recentes de várias bibliotecas (por exemplo React 19.3, Vite 8, Pydantic 2.14); não avaliei maturidade nem compatibilidade de longo prazo.

### 10.3 Testes

- **[Fato]** Backend: 14 testes de integração, cobrindo as 3 rotas e os principais erros. Não há testes unitários isolados, de configuração (`run()`), nem de `schema.sql` em banco já existente.
- **[Fato]** Frontend: nenhum teste, lint ou typecheck.
- **[Fato]** Nenhuma execução automática de testes (sem CI). **[Inferência]** a única garantia hoje é a execução manual.
- **[Fato]** Os testes dependem de um PostgreSQL disponível e apagam as tabelas (seção 7).

### 10.4 Continuidade e independência operacional

- **[Fato]** Repositório em conta pessoal (`danielxdrj/forge`), um único autor, sem `CODEOWNERS`, sem `LICENSE`. **[Inferência]** conflita com o requisito de que credenciais e recursos fiquem sob controle institucional da empresa; precisa de decisão (seção 13).
- **[Fato]** Ponto positivo para a transferência de conhecimento: documentação extensa, protocolo de execução e specs por etapa já existem (`.specs/`, `docs/`). **[Inferência]** parte dela está desatualizada (seção 8) e foi escrita para um escopo diferente do descrito no enunciado.
- **[Fato]** Não existe ainda nenhum procedimento manual equivalente documentado para automações, porque não há automações.

### 10.5 Segurança da aplicação (estado atual)

- **[Fato]** API sem autenticação, sem CORS e sem limite de tamanho para o texto do log (`EvidenceCreate.content` só exige `min_length=1`; a pendência está registrada em `docs/ROADMAP.md`, Etapa 02).
- **[Fato]** O Compose publica o PostgreSQL e o frontend só em `127.0.0.1` (`docker-compose.yml`).
- **[Fato]** O endereço de escuta da API não tem padrão: `FORGE_HOST`/`FORGE_PORT` obrigatórios (`backend/app/main.py`). Se alguém definir `0.0.0.0`, a API fica exposta sem autenticação. **[Inferência]** risco só se o operador fizer isso.

## 11. Alternativas para onde guardar este relatório (repositório × Notion)

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

## 12. Recomendação, decisões para aprovação e próximos passos

Recomendação justificada (limitada ao escopo de análise; nada disso foi implementado):

1. Tratar este levantamento como entrada de FRG-23, FRG-9 e FRG-25. O que existe hoje é pequeno (cerca de 200 linhas de Python de aplicação e 1 mil linhas de interface), então a base reaproveitável provavelmente é mais a documentação e as regras (`AGENTS.md`, `.specs/`) do que o código. **[Inferência]**
2. Antes de FRG-25 (arquitetura-alvo), alinhar a visão: o repositório descreve um copiloto individual de investigação; o enunciado descreve uma ferramenta interna da empresa com agentes, automações e continuidade institucional. Sem alinhar, a arquitetura-alvo parte de premissas diferentes. **[Inferência]**
3. Não escolher linguagem, banco ou arquitetura final com base só neste relatório: o stack atual (Python/FastAPI/PostgreSQL/React) é uma decisão "aprovada para a primeira implementação" (`README.md`), não necessariamente a decisão final.

**Decisões para aprovação do responsável:**

- Onde manter este relatório (seção 11).
- Se o repositório deve continuar público e na conta pessoal.
- Se a divergência de visão (seção 13, pergunta 1) será resolvida antes de FRG-23 e FRG-25.

## 13. Perguntas em aberto

1. **Visão do produto:** o Forge é o "copiloto local de investigação, uso individual" que `README.md` e `.specs/PROJECT_CONTEXT.md` descrevem, ou a ferramenta interna de automação e coordenação de agentes descrita no enunciado desta tarefa? Os documentos do repositório devem ser atualizados para refletir a visão correta?
2. **Diagrama de arquitetura com a visão ampla (inclusive SaaS):** onde ele está? Não está no repositório (apenas os 2 blocos Mermaid em `docs/ARCHITECTURE.md`, sem SaaS). Preciso de acesso para as próximas tarefas (somente leitura).
3. **Propriedade do repositório:** o repositório `danielxdrj/forge` deve migrar para uma organização da Ferreira & Borzone? Deve ser privado? Quem deve ter permissão de administração além do autor atual?
4. **GitHub Actions, GHCR e Portainer:** onde estão hoje o CI e o deploy mencionados no planejamento? Eles pertencem a outros repositórios? O Forge precisará ser publicado como imagem (hoje só o frontend tem Dockerfile)?
5. **n8n:** há alguma instância ou fluxo já existente que deva ser considerado em FRG-9? O repositório não tem nenhuma referência.
6. **Docker/Compose:** alguém já executou `docker compose up` neste repositório com o `.env` real? Não pude verificar (Docker ausente na VM).
7. **Versão de Python e política de dependências:** qual versão é a oficial? Aceita-se fixar dependências do backend (isso é correção e ficou fora do escopo desta tarefa)?
8. **Banco de teste:** a suíte pode ser rodada contra o mesmo banco usado no desenvolvimento? Hoje ela apaga os dados (`TRUNCATE`).
9. **Autoria:** os dois e-mails do histórico (`Carlos Daniel`) são da mesma pessoa? Algum deles é de conta pessoal que deva ser substituído por conta institucional?
10. **Licença:** o repositório público deve ter licença ou ser privado? Hoje não há `LICENSE`.
11. **Documentação divergente:** posso listar a atualização de `README.md` e `docs/ARCHITECTURE.md` (seção 8) como tarefa própria? Nada foi alterado aqui.
12. **Tarefas anteriores:** o enunciado menciona "documentação já produzida pelas tarefas anteriores", mas esta é a primeira (sem dependências). Existe algum material fora do repositório (Notion, Drive etc.) que eu deveria considerar?

## 14. Limitações desta análise

- Docker não estava disponível: `docker-compose.yml` e `frontend/Dockerfile` foram lidos, não executados. O build do frontend foi feito com `npm` direto.
- Os testes foram executados com um PostgreSQL 16 do pacote Ubuntu, não com a imagem `postgres:16` do Compose.
- Não avaliei qualidade de design visual do frontend nem desempenho.
- A leitura de `.specs/steps/03..08` foi parcial (confirmei estado "bloqueada" e as pendências citadas no roadmap). Não fiz auditoria linha a linha desses arquivos.
- Não consultei fontes externas (documentação oficial) porque nada na análise exigiu uma afirmação sobre comportamento de produto de terceiros. As versões "mais recentes" vêm de `npm outdated` e `pip` em 2026-11-06.
