# Runbook: container local do Forge (ADR-017)

Painel e Core no Docker Compose `forge`. Um comando sobe Postgres 16, o backend JSON e o `forge_frontend` (nginx) em `http://127.0.0.1:8090`. A origem do navegador é só essa: a UI estática e `/api/` no mesmo host.

**Não** use o `docker-compose.yml` legado para isto. **Não** publique o Postgres em `0.0.0.0`. O backend **não** publica a 8091 no host (só o nginx alcança `forge_backend:8091` na rede compose).

## Conflito na porta 5433

O padrão deste compose é `127.0.0.1:5433`. O [`docker-compose.dev.yml`](../../docker-compose.dev.yml) (projeto `forge_dev`, ADR-004) **também** publica Postgres em `127.0.0.1:5433`. Os dois **não** podem estar no ar nessa porta.

- Parar o compose de dev: `docker compose -f docker-compose.dev.yml down`
- Ou mudar só o painel: `$env:FORGE_PG_HOST_PORT = "5434"` (PowerShell) / `FORGE_PG_HOST_PORT=5434` (bash)

Nenhum job de CI usa `docker-compose.dev.yml`; os testes de Postgres sobem um serviço efêmero na 5432 do runner.

CI e testes unitários **não** chamam GitHub nem Cursor reais.

## Variáveis (só no ambiente, nunca no Git)

| Nome | Uso |
| --- | --- |
| `FORGE_PG_OWNER_PASSWORD` | dono/migrador (`forge_owner`); `POSTGRES_PASSWORD_FILE` |
| `FORGE_PG_APP_PASSWORD` | escritor `forge_app` |
| `FORGE_PG_READONLY_PASSWORD` | leitor `forge_readonly` (HeidiSQL/DBeaver). **Obrigatória**: primeiro boot falha fechado se faltar ou estiver vazia |
| `FORGE_GITHUB_CLIENT_ID` | client id **público** do OAuth App com Device Flow |
| `FORGE_PG_HOST_PORT` | porta do Postgres no loopback do host (padrão `5433`) |
| `FORGE_FRONTEND_HOST_PORT` | origem do navegador (padrão `8090`) |
| `FORGE_CURSOR_MODEL` | opcional; modelo da assinatura Cursor (sem default de custo) |

A senha **não** vai para arquivo no repositório. O compose lê as variáveis como `secrets.environment`.

A senha de cada papel é gravada no volume `forge_pgdata` no **primeiro boot**. Depois disso, mudar é `ALTER ROLE ... PASSWORD` (não basta trocar a env e reiniciar).

Não passe URL de banco nem senha na linha de comando. O `auth.cli` dentro do container monta as URLs a partir de `/run/secrets`.

## PowerShell (Windows) — ponta a ponta

```powershell
$env:FORGE_PG_OWNER_PASSWORD = '<SEGREDO>'
$env:FORGE_PG_APP_PASSWORD = '<SEGREDO>'
$env:FORGE_PG_READONLY_PASSWORD = '<SEGREDO>'
$env:FORGE_GITHUB_CLIENT_ID = '<CLIENT_ID_PUBLICO_DO_OAUTH_APP>'
# opcional: $env:FORGE_PG_HOST_PORT = '5434'
# opcional: $env:FORGE_CURSOR_MODEL = '<MODELO_DA_ASSINATURA>'
Set-Location <CAMINHO_DO_REPO>
docker compose -f docker-compose.forge.yml up -d --build
```

Bash equivalente: exporte as mesmas variáveis e rode o `docker compose`.

## Login gh e Cursor CLI (dentro do container, como usuário `forge`)

As ferramentas estão **na imagem**. Credenciais ficam no volume `forge_cli_home` (`HOME` do usuário `forge`, uid 1000). Não monte keyring, `HOME`/`APPDATA` nem `docker.sock` do Windows. **Não** use `docker compose exec -u 0`: `gh`, `cursor-agent` e `python -m forge_core.auth.cli` correm como `forge`.

```powershell
docker compose -f docker-compose.forge.yml exec forge_backend gh auth login
docker compose -f docker-compose.forge.yml exec forge_backend cursor-agent login
```

Siga o device flow que o comando mostrar. Sem `GH_TOKEN` / `GITHUB_TOKEN`.

Se um volume antigo `forge_cli_home` estiver com dono root: uma vez, `docker compose -f docker-compose.forge.yml exec -u 0 forge_backend chown -R forge:forge /home/forge`. Volume **novo** já nasce com uid 1000.

## Bootstrap do owner e papel editor

O owner **não** implica editor. Quem vai criar tarefas precisa dos dois. Cada comando pede um device flow no terminal (ADR-014). O id tem de ser o da conta que autorizar. **Não** informe `FORGE_DATABASE_URL` nem senha neste `exec`:

```powershell
docker compose -f docker-compose.forge.yml exec forge_backend python -m forge_core.auth.cli bootstrap --expect-github-id <ID_NUMERICO>
docker compose -f docker-compose.forge.yml exec forge_backend python -m forge_core.auth.cli grant --github-id <ID_NUMERICO> --role editor
```

## Abrir o painel e criar uma tarefa

```powershell
Start-Process 'http://127.0.0.1:8090'
```

1. **Entrar com GitHub**: a página mostra o `user_code` e o link de verificação. Autorize no GitHub; a página consulta `/api` sozinha.
2. `/api/auth/whoami` (via UI) lista login e papéis. Sem `editor`, a tela de tarefas explica que o owner não basta.
3. **Nova tarefa**: escolha um repositório da allowlist (org `ferreiraeborzone`), cole o contexto escrito (máx. 64 KiB; sem imagem) e **Gerar rascunho**.
4. Confira a pré-visualização (saída do LLM: não é HTML). Preencha Tipo, Prioridade e Size (opções do board IT Backlog, projeto 13).
5. **Confirmar e publicar**: o backend recusa se o `preview_hash` mudou. Issue, item do board e branch entram em `task_links`. Se falhar no meio, **Confirmar** de novo retoma; não duplica a issue.
6. A lista **Tarefas** mostra repositório, título, fase/status, link da issue e da PR (se o `gh` achar a PR da branch).

O token GitHub não é gravado. A sessão Forge vai num cookie HttpOnly, SameSite=Strict, Path=/, prazo padrão 8 h. CSRF: cookie legível `forge_csrf` + cabeçalho `X-CSRF-Token` em todo não-GET.

## HeidiSQL e DBeaver (somente leitura)

Use **sempre** `forge_readonly`. Não use `forge_owner` no cliente SQL (é o migrador/superuser desta instância local).

| Campo | Valor |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `5433` (ou o valor de `FORGE_PG_HOST_PORT`) |
| Database | `forge` |
| User | `forge_readonly` |
| Password | a mesma que você pôs em `FORGE_PG_READONLY_PASSWORD` (não está neste runbook) |
| SSL | desligado no loopback local |

Este papel tem SELECT nas tabelas, **exceto** `sessions.token_hash`. Sem INSERT/UPDATE/DELETE/DDL.

Rascunhos e vínculos depois de criar uma tarefa:

```sql
SELECT id, task_id, repo, status, preview_hash, created_at FROM drafts ORDER BY created_at;
SELECT id, task_id, kind, repo, number, url, board_item_id, created_at FROM task_links ORDER BY created_at;
```

## Backup

```powershell
docker compose -f docker-compose.forge.yml exec forge_postgres pg_dump -U forge_owner -d forge -Fc -f /tmp/forge.dump
docker compose -f docker-compose.forge.yml cp forge_postgres:/tmp/forge.dump .\forge.dump
```

Guarde o dump fora do Git. Restaure só em ambiente de teste.

## Troubleshooting

| Sintoma | O que fazer |
| --- | --- |
| `Bind for 0.0.0.0:5433 failed` / porta em uso | Outro Postgres (compose de dev). `down` nele ou `FORGE_PG_HOST_PORT` |
| `forge-init: segredo ausente/vazio` | Defina as três senhas no ambiente **antes** do primeiro `up` (volume novo) |
| `forge-web: segredo ausente` | O backend não leu `/run/secrets/...`; conferir `secrets:` no compose |
| `forge-auth: FORGE_DATABASE_URL é obrigatória` | Comando rodou **fora** do container. Dentro, os arquivos de segredo preenchem a URL |
| `host_rejected` | Host fora da allowlist. Padrão: 127.0.0.1/localhost nas portas 8090 e 8091 |
| `csrf` | Recarregue a página e tente de novo (cookie `forge_csrf` + cabeçalho `X-CSRF-Token`) |
| `forbidden` ao gerar/confirmar | Falta papel `editor` (owner sozinho não basta) |
| `diff_changed` | A pré-visualização mudou; atualize tipo/prioridade/size e confirme de novo |
| `device_flow_disabled` | Habilite Device Flow no OAuth App |
| Página em 8091 recusada / conexão recusada | A 8091 do backend **não** é publicada. Use `http://127.0.0.1:8090` |
| `gh` / `cursor-agent` sem permissão em `/home/forge` | Volume antigo como root: `chown` uma vez como uid 0 (passo acima) |
| Volume antigo, senha nova ignorada | A senha do papel já está no PGDATA; `ALTER ROLE` |
