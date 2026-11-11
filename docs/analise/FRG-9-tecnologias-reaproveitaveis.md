# Tecnologias e componentes reaproveitáveis (FRG-9)

Fase 0 — Análise. Estudo sem implementação. Nenhum código de produção foi alterado, nenhum build foi executado e nenhuma dependência foi instalada.

| Item | Valor |
| --- | --- |
| Data da análise | 2026-11-06 (UTC) |
| Base | `main` em `92aee6d` (inclui PR #10, FRG-32, e PR #11, automação de release) |
| Dependência | FRG-32, concluída: [`docs/analise/FRG-32-inspecao-repositorio.md`](FRG-32-inspecao-repositorio.md). Usada como ponto de partida; só foram conferidos no repositório os pontos listados abaixo. |
| Destino | Insumo de FRG-25 (Definir arquitetura-alvo) |

Convenção: **[Fato]** verificado em arquivo do repositório (com caminho) ou no relatório FRG-32. **[Inferência]** interpretação minha. **[Opinião]** juízo de qualidade ou recomendação, a ser confirmado.

**Atualização (2026-11-11):** a automação release-please foi removida. Releases são manuais; a versão fica em `pyproject.toml`. Ver [`docs/RELEASES.md`](../RELEASES.md). O check de título de PR permanece.

## 1. Resumo

- **[Fato]** O código existente é legado de outro projeto (copiloto de investigação com FastAPI, PostgreSQL e React). Não há agentes, orquestração, filas, integração com GitHub, GHCR, Portainer ou n8n (FRG-32, seção 9).
- **[Fato]** Desde o FRG-32, a `main` ganhou a automação de release (PR #11): `.github/workflows/pr-title.yml`, `.github/workflows/release.yml`, `release-please-config.json`, `.release-please-manifest.json` e `docs/RELEASES.md`. Esse item é o único com valor de CI reaproveitável e não depende do legado. O FRG-32 (seção 5 e 10.1) afirmava que não havia `.github/`; essa afirmação está desatualizada.
- **Recomendação:** não reaproveitar código, arquitetura nem stack do legado como base do Forge. Reaproveitar apenas convenções e a infraestrutura de CI/release que não depende do legado, com as adaptações listadas na matriz. As decisões ficam para FRG-25.

## 2. Verificações feitas nesta tarefa

| Verificação | Resultado | Evidência |
| --- | --- | --- |
| Arquivos versionados | 63 arquivos | `git ls-files` |
| Workflows de CI | 2: título de PR e release | `.github/workflows/pr-title.yml`, `.github/workflows/release.yml` |
| Ação de release fixada por SHA | Sim, `googleapis/release-please-action` em `v5.0.0` | `.github/workflows/release.yml` |
| Desativação da release | Variável `RELEASE_AUTOMATION_ENABLED` = `false` | `.github/workflows/release.yml` |
| Dockerfile do frontend | Build em `node:22-alpine` e publicação em `nginx:1.27-alpine`, sem usuário não-root explícito | `frontend/Dockerfile` |
| Compose | `postgres:16` e `frontend`, portas em `127.0.0.1`, variáveis sem valor padrão | `docker-compose.yml` |
| Dependências Python | Sem versão fixada, sem lockfile | `backend/requirements.txt` |
| `.gitignore` | Cobre `.env`, `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `node_modules/`, `dist/`; não cobre `.env.*`, `*.pem`, `*.key` | `.gitignore` |
| Licença | Não há `LICENSE`; `frontend/package.json` não declara campo `license` | `git ls-files` e `grep "license"` |
| Testes do frontend, lint e typecheck | Não existem | FRG-32, seção 7 |

## 3. Critérios de classificação

- **Reaproveitar como está:** atende ao papel sem mudança de conteúdo, não depende do legado e tem evidência no repositório.
- **Reaproveitar com adaptação:** a ideia ou o padrão servem, mas o conteúdo é do legado ou precisa de ajuste de escopo.
- **Substituir:** o papel é necessário, mas a implementação legada não serve ao Forge (linguagem, banco, framework ou escopo diferentes).
- **Descartar:** sem valor para o Forge; só após aprovação do responsável.
- **Esforço:** P (até um arquivo ou uma regra), M (alguns arquivos ou um fluxo), G (módulo ou decisão de arquitetura).
- Risco de manter: o que muda se o item continuar; risco de substituir: o que muda se o item for trocado.

## 4. Matriz

Componentes previstos no planejamento: Forge API, Orchestrator, Agent Runtime, Queue / Event Bus, Plugin Registry, Context Manager, Persistent Storage, Audit Logs e Integração com GitHub.

| Componente/tecnologia existente | Caminho | Componente do Forge onde poderia ser usado | Classificação | Justificativa (evidência) | Esforço | Risco de manter / de substituir |
| --- | --- | --- | --- | --- | --- | --- |
| Workflow de título de PR (Conventional Commits) | `.github/workflows/pr-title.yml` | Integração com GitHub (convenção de entrega) | Reaproveitar como está | **[Fato]** Valida o título com regex e comentário explica que o título vira a mensagem do commit. Não depende do legado. | P | Baixo. Manter exige que o padrão seja aceito pela equipe. |
| Workflow de release (release-please) | `.github/workflows/release.yml`, `release-please-config.json`, `.release-please-manifest.json` | Integração com GitHub (CI/release); Audit Logs (histórico de versões) | Removida (2026-11-11) | **[Fato]** Ação existia, fixada por SHA e desativável por variável. A automação foi retirada; releases são manuais (`docs/RELEASES.md`). | P | — |
| Convenção de Conventional Commits e tags semver | histórico git; `docs/RELEASES.md` | Convenções transversais | Reaproveitar como está | **[Fato]** Mensagens majoritariamente em Conventional Commits (FRG-32, seção 4); documentado em `docs/RELEASES.md`. | P | Baixo. |
| Protocolo de execução por etapa | `.specs/EXECUTION_PROTOCOL.md` | Processo de desenvolvimento (não é componente de software) | Reaproveitar com adaptação | **[Fato]** Descreve passos pequenos, branch a partir de `main`, teste e revisão de diff. **[Inferência]** referências a etapas do legado (`IMPLEMENTATION_PLAN.md`, `steps/`) precisam ser trocadas. | P | Baixo. |
| Regras de segurança para agentes | `AGENTS.md` | Plugin Registry e Context Manager (regras de acesso); Audit Logs | Reaproveitar com adaptação | **[Fato]** Regras de leitura, segredo fora do Git, placeholders e parar-e-perguntar. **[Fato]** A regra "integrações somente leitura" é específica do escopo do legado. **[Inferência]** precisa de revisão com o responsável (pergunta 9 do FRG-32). | P | Médio. |
| `.gitignore` | `.gitignore` | Convenção de segredos (transversal) | Reaproveitar com adaptação | **[Fato]** Cobre `.env` e build de Python/Node, mas não `.env.*`, `*.pem` ou `*.key`. | P | Baixo. Acrescentar padrões de segredo. |
| `.env.example` com placeholders | `.env.example` | Configuração de Forge API e Persistent Storage | Reaproveitar com adaptação | **[Fato]** Placeholders óbvios (`<SENHA>`, `<HOST>`). **[Inferência]** o padrão é bom; as variáveis são do legado. | P | Baixo. |
| Docker Compose do legado | `docker-compose.yml` | Infra de execução local (Persistent Storage, Forge API) | Descartar | **[Fato]** Sobe `postgres:16` e um frontend do legado; variáveis sem padrão. **[Inferência]** um Compose pronto induziria a escolha de banco e serviços antes de FRG-25. Manter só a convenção de publicar portas em `127.0.0.1`. | P | Médio se mantido (induz a stack). Substituir é simples. |
| Dockerfile do frontend (multi-stage) | `frontend/Dockerfile` | Deploy em Portainer (futuro) | Substituir | **[Fato]** Build em Node 22 e nginx 1.27 para uma tela do legado. **[Inferência]** o padrão multi-stage é genérico, mas o Forge ainda não definiu uma interface web nem imagem publicada (GHCR). | P | Baixo. Refazer quando a imagem for decidida. |
| Dockerfile do backend | — | Forge API, Orchestrator | Substituir (não existe) | **[Fato]** Não existe no repositório (FRG-32, seção 5). Nada a reaproveitar. | — | — |
| CI de testes, GHCR, Portainer | — | Integração com GitHub (CI/deploy) | Substituir (não existe) | **[Fato]** Não há workflow de testes nem publicação de imagem. **[Informado no FRG-32]** o CI e o deploy do planejamento estão em outro lugar (pergunta 4). | — | — |
| Backend FastAPI + psycopg | `backend/app/main.py`, `backend/app/db.py`, `backend/requirements.txt` | Forge API, Persistent Storage | Substituir | **[Fato]** 3 rotas de investigação; sem versões fixadas e sem lockfile (FRG-32, seção 6). **[Inferência]** a stack não está decidida; o legado só é candidato se FRG-25 escolher Python e PostgreSQL. Não adotar como base sem análise. | M | Alto se mantido como base: a arquitetura do legado (rotas em um módulo, schema por `CREATE TABLE IF NOT EXISTS` no startup) não tem migrações. |
| Schema SQL de investigações | `backend/app/schema.sql` | Persistent Storage | Descartar | **[Fato]** Tabelas `investigations` e `evidence`, sem migrações (FRG-32, seção 8). | P | Baixo. |
| Testes de integração do legado | `backend/tests/test_investigations.py` | Referência de testes de Forge API | Descartar | **[Fato]** Usam `TRUNCATE` no banco apontado por `DATABASE_URL`, sem banco separado (FRG-32, seção 7). **[Inferência]** risco de apagar dados reais. | P | Alto se executados contra banco real. |
| Frontend React 19 + Tailwind 4 | `frontend/src/`, `frontend/package.json`, `frontend/package-lock.json` | Interface do Forge (se houver) | Descartar | **[Fato]** Tela sem chamadas HTTP, sem testes, lint nem typecheck (FRG-32, seções 7 e 8). Lockfile e versões exatas são boas práticas, mas servem ao legado. | M | Médio. Componentes genéricos (`Button`, `Modal`, `Tabs`, `Pagination`) podem ser consultados se houver interface web. |
| Dependências do frontend sem auditoria | `frontend/package.json` | — | Descartar | **[Fato]** Sem vulnerabilidades conhecidas em 2026-11-06 (FRG-32, seção 11.2). | — | — |
| Documentação de produto, arquitetura e roadmap | `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LEARNING_GUIDE.md`, `docs/IMPLEMENTATION_PLAN.md`, `README.md` | Documentação do Forge | Descartar ou arquivar | **[Fato]** Descrevem o copiloto de investigação. **[Fato]** `docs/ARCHITECTURE.md` contém Mermaid do legado; FRG-32 registra divergências entre os documentos. | M | Alto se mantidos sem aviso: induzem a erro quem chegar ao repositório. |
| Specs por etapa | `.specs/steps/01..08` | — | Descartar ou arquivar | **[Fato]** Descrevem o legado. | P | Baixo. |

Itens não encontrados no repositório (sem nada a reaproveitar): agentes, orquestração, filas e event bus, plugin registry, context manager, audit logs, integração com GitHub por API, GHCR, Portainer e n8n (FRG-32, seção 9).

## 5. Tecnologias presentes que podem ser mantidas

Mantidas porque não dependem de decisão de stack:

1. Conventional Commits, validados por `.github/workflows/pr-title.yml`.
2. ~~Release automatizada com release-please~~ **Removida (2026-11-11).** Releases manuais: [`docs/RELEASES.md`](../RELEASES.md).
3. Ações do GitHub fixadas por SHA (`.github/workflows/release.yml`). Convenção de segurança a manter em novos workflows.
4. Portas publicadas em `127.0.0.1` (`docker-compose.yml`). Convenção a manter, se houver Compose.
5. Placeholders em `.env.example`.

Tecnologias do legado (Python, FastAPI, psycopg, PostgreSQL 16, React 19, Vite, Tailwind, Node 22, nginx) **não** são mantidas por esta análise. São candidatas apenas se FRG-25 escolher, e nesse caso como alternativa comparada.

## 6. Riscos

**Manter itens do legado:**

- Induzir a stack e a arquitetura por inércia (viés de stack).
- Misturar documentos do legado com os do Forge atual, gerando decisões erradas.
- Herdar a numeração `0.9.0` e o histórico de tags do legado na automação de release.
- Dependências Python sem versão fixada e sem lockfile: build não reprodutível.
- Repositório público em conta pessoal, sem licença: risco de continuidade e de exposição.

**Substituir itens:**

- Perda de consulta ao legado, se não houver marco de arquivo (tag ou branch) antes da remoção (FRG-32, seção 13).
- Retrabalho de CI e de imagem Docker, porque nada disso existe para o Forge atual.
- Pode haver divergência entre a convenção de release do PR #11 e a escolha final de versionamento.

**Riscos de segurança (herdados):**

- `.gitignore` não cobre `.env.*`, `*.pem` e `*.key` (regra de `AGENTS.md`).
- Não há varredura automática de segredos (sem pre-commit e sem CI de segredos).
- Testes do legado apagam dados do banco apontado por `DATABASE_URL`.

## 7. Decisões para FRG-25

1. Stack de linguagem, framework e banco do Forge. O legado não deve orientar essa escolha. Alternativas a comparar: Python com FastAPI ou outro framework; TypeScript com Node; outros. Critérios sugeridos: aderência aos componentes previstos, facilidade de transferência para outro desenvolvedor, custo de manutenção e licenças.
2. Destino do legado: alternativas A (tag e branch de arquivo, depois remoção), B (pasta `legacy/`), C (novo repositório), D (remoção) ou E (manter com aviso), conforme FRG-32, seção 13. Recomendação provisória do FRG-32: A ou C.
3. Versionamento: continuar `0.9.0` (como a automação do PR #11 pressupõe) ou recomeçar em `0.1.0`. Decisão antes de mergear o PR #11.
4. Repositório do Forge atual: o mesmo (`danielxdrj/forge`, público, conta pessoal) ou um novo, sob controle institucional e, se possível, privado.
5. Política de regras de `AGENTS.md`: quais princípios valem para o Forge atual (FRG-32, pergunta 9).
6. Local de CI e deploy (GitHub Actions, GHCR e Portainer): onde estão e se o Forge atual será publicado como imagem (FRG-32, pergunta 4).
7. Licença do repositório (FRG-32, pergunta 11).

## 8. Perguntas em aberto

1. Confirmar o destino do legado (decisão 2). Quem aprova?
2. ~~Confirmar que o PR #11 (automação de release) deve permanecer na `main`~~ **Resolvido (2026-11-11):** a automação foi removida; releases são manuais.
3. Há material fora do repositório (Notion, Drive, diagrama de arquitetura com visão SaaS) que deva ser considerado? Esta análise não o acessou.
4. n8n: há instância ou fluxo existente? Não há nenhuma referência no repositório.

## 9. Limitações

- A classificação de "reaproveitar" depende do conteúdo do repositório em 2026-11-06 e da premissa informada de que o código é legado (FRG-32, seção 1).
- Nenhuma fonte externa foi consultada (documentação oficial de release-please, Docker ou licenças). Afirmações sobre essas ferramentas são [Inferência] e precisam de consulta antes de virar decisão.
- Não foram executados testes, builds nem auditorias de dependência nesta tarefa. Os resultados de FRG-32 foram usados como referência.
