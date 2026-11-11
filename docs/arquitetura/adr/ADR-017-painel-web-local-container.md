# ADR-017: painel web local em container (Core + FastAPI)

- **Status:** Aceito (11/11/2026), por decisão do responsável.
- **Data:** 2026-11-11.
- **Relaciona:** ADR-004 (Postgres), ADR-005 (segredos fora do Git), ADR-013 (sandbox de agentes), ADR-014 (auth humana), ADR-015 (Cursor CLI / gh).

## Contexto

O Core já persiste em Postgres, autentica pessoas por device flow na CLI e rascunha issues com Cursor CLI + gh. Falta um painel local para a operação diária. Esta entrega (PR A) sobe o Core e uma API JSON de login num container, com Postgres 16 no mesmo compose. A tela de tarefas é o PR B.

## Decisões

- **D1. Runtime.** O painel e o Core rodam no serviço `forge_backend` da imagem `deploy/web/Dockerfile`. Distinto do sandbox de agentes (ADR-013 / FRG-6): o filho do orquestrador continua `--network none`, descartável, sem Docker socket. O backend do painel tem egresso para `github.com` / `api.github.com` (device flow, `gh`) e para os hosts da Cursor CLI. Um worker uvicorn (`workers=1`) porque o device flow pendente vive em memória.
- **D2. Compose.** Arquivo novo `docker-compose.forge.yml`, `name: forge`. Serviços com `container_name` igual: `forge_postgres` e `forge_backend`. `forge_frontend` (PR B) não entra neste PR: será nginx em `127.0.0.1:8090`, UI estática e reverse-proxy de `/api/` para `forge_backend`, origem única no navegador. O `docker-compose.yml` legado não é alterado na função; só marcado como legado. `docker-compose.dev.yml` permanece para testes manuais (ADR-004) e **conflita na 5433** com o padrão deste compose.
- **D3. Interface.** Extra opcional `[web]`: FastAPI, Jinja2, uvicorn. Testes do Core sem `[web]` não precisam dessas libs. API em JSON sob `/api/`. HTML mínimo de login/logout/whoami no backend só até o PR B. Sem tela de tarefas.
- **D4. Bind e publicação.** Dentro da rede compose o backend escuta `0.0.0.0:8091` para o proxy futuro alcançar. No host, publicação opcional **só em loopback** `127.0.0.1:${FORGE_BACKEND_HOST_PORT:-8091}:8091`, documentada como teste do PR A. Postgres: `127.0.0.1:${FORGE_PG_HOST_PORT:-5433}:5432`. Nunca `0.0.0.0`.
- **D5. Host e proxy.** Allowlist de `Host`: `127.0.0.1:8090`, `localhost:8090`, `127.0.0.1:8091`, `localhost:8091` (configurável). Sem CORS. `X-Forwarded-*` **não é confiável por padrão** (`FORGE_TRUST_FORWARDED=false`). No PR B, ligar só para os IPs do `forge_frontend` na rede compose (`FORGE_TRUSTED_PROXIES`).
- **D6. Sessão e CSRF.** Cookie `forge_session`: HttpOnly, SameSite=Strict, Path=/, Secure configurável (desligado em HTTP local). CSRF double-submit: cookie legível `forge_csrf` + cabeçalho `X-CSRF-Token` em todo não-GET (formulários HTML também enviam `csrf_token`). Device flow pendente: id opaco HttpOnly atado ao navegador, estado só em memória, TTL. Token GitHub só em memória, descartado depois de `/user`; no banco só `token_hash`. Sessão web tem `expires_at` (padrão 8 h). Sessão CLI continua sem prazo (`expires_at` NULL). Logout grava `session_revocations`. Owner **não** implica editor.
- **D7. Segredos e papéis.** Compose `secrets` com `environment:` (`FORGE_PG_OWNER_PASSWORD`, `FORGE_PG_APP_PASSWORD`, `FORGE_PG_READONLY_PASSWORD`) montados em `/run/secrets`. Postgres usa `POSTGRES_PASSWORD_FILE`. URLs de banco montadas em runtime a partir dos arquivos; falha fechado se faltar. Três papéis: `forge_owner` (migrações), `forge_app` (menor privilégio, `postgres_roles.sql`), `forge_readonly` (SELECT; em `sessions` sem `token_hash`, privilégio por coluna). O leitor **é criado no primeiro boot**; senha ausente ou vazia **falha fechado** (não há skip). SQLite só em testes/CI.
- **D8. CLIs.** `gh` (2.81.0) e Cursor Agent (`2026.11.10-731fb78`) instalados **na imagem**, com SHA-256. Login uma vez dentro do container (`docker compose exec forge_backend gh auth login` / `cursor-agent login`). Credenciais no volume nomeado `forge_cli_home` (`HOME` do usuário `forge`). Sem mount de keyring/HOME/APPDATA/`~/.config/gh` do host, sem `docker.sock`, sem `GH_TOKEN`/`GITHUB_TOKEN`. Allowlist de env (ADR-015) e `--mode ask` + temp dir continuam.
- **D9. Semente.** Projeto `FORGE` e cinco repositórios da org `ferreiraeborzone`, idempotente. `default_branch = main` é placeholder, não conferido no GitHub. Helper `list_active_allowed_repos` para o PR B.

## Alternativas

| Opção | Por que não |
| --- | --- |
| Bind 127.0.0.1 *dentro* do container | O `forge_frontend` na rede compose não alcançaria o backend. |
| Confiar em `X-Forwarded-*` já neste PR | A publicação 8091 aceitaria Host forjado. |
| Papel leitor opcional se a senha faltar | Inconsistente com falha fechada dos outros segredos. |
| HTML como produto | O PR B move a UI para o frontend; o HTML daqui é apoio ao login. |

## Consequências

Quem opera sobe um compose, entra pelo device flow no navegador e usa HeidiSQL/DBeaver no loopback com `forge_readonly`. Risco residual aceito: credenciais CLI no volume Docker (não no keyring do SO); o backend tem egresso para GitHub e Cursor. O sandbox de agentes não muda.
