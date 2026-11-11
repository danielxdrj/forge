# Runbook: container local do Forge (ADR-017)

Painel e Core no Docker Compose `forge`. Um comando sobe Postgres 16 e o backend. A tela de tarefas é o PR B (`forge_frontend` em `http://127.0.0.1:8090`).

**Não** use o `docker-compose.yml` legado para isto. **Não** publique o Postgres em `0.0.0.0`.

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
| `FORGE_PG_HOST_PORT` | porta no loopback do host (padrão `5433`) |
| `FORGE_BACKEND_HOST_PORT` | publicação de **teste** do backend (padrão `8091`) até o frontend |

A senha **não** vai para arquivo no repositório. O compose lê as variáveis como `secrets.environment`.

A senha de cada papel é gravada no volume `forge_pgdata` no **primeiro boot**. Depois disso, mudar é `ALTER ROLE ... PASSWORD` (não basta trocar a env e reiniciar).

## PowerShell (Windows)

```powershell
$env:FORGE_PG_OWNER_PASSWORD = '<SEGREDO>'
$env:FORGE_PG_APP_PASSWORD = '<SEGREDO>'
$env:FORGE_PG_READONLY_PASSWORD = '<SEGREDO>'
$env:FORGE_GITHUB_CLIENT_ID = '<CLIENT_ID_PUBLICO_DO_OAUTH_APP>'
# opcional: $env:FORGE_PG_HOST_PORT = '5434'
Set-Location <CAMINHO_DO_REPO>
docker compose -f docker-compose.forge.yml up -d --build
Start-Process 'http://127.0.0.1:8091'
```

Bash equivalente: exporte as mesmas variáveis e rode o `docker compose`.

Abra `http://127.0.0.1:8091` (teste do PR A). No PR B a origem do navegador será `http://127.0.0.1:8090`.

## Login gh e Cursor CLI (dentro do container)

As ferramentas estão **na imagem**. Credenciais ficam no volume `forge_cli_home` (`HOME` do usuário `forge`). Não monte keyring, `HOME`/`APPDATA` nem `docker.sock` do Windows.

```powershell
docker compose -f docker-compose.forge.yml exec forge_backend gh auth login
docker compose -f docker-compose.forge.yml exec forge_backend cursor-agent login
```

Siga o device flow que o comando mostrar. Sem `GH_TOKEN` / `GITHUB_TOKEN`.

## Bootstrap do owner e papel editor

O owner **não** implica editor. Quem vai criar tarefas (PR B) precisa dos dois.

```powershell
docker compose -f docker-compose.forge.yml exec forge_backend python -m forge_core.auth.cli bootstrap --expect-github-id <ID_NUMERICO>
docker compose -f docker-compose.forge.yml exec forge_backend python -m forge_core.auth.cli grant --github-id <ID_NUMERICO> --role editor
```

Cada comando pede um device flow no terminal (ADR-014). O id tem de ser o da conta que autorizar.

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

## Backup

```powershell
docker compose -f docker-compose.forge.yml exec forge_postgres pg_dump -U forge_owner -d forge -Fc -f /tmp/forge.dump
docker compose -f docker-compose.forge.yml cp forge_postgres:/tmp/forge.dump .\forge.dump
```

Guarde o dump fora do Git. Restaure só em ambiente de teste.

## Login web (device flow)

1. Abra `http://127.0.0.1:8091` → Entrar com GitHub.
2. A página mostra o `user_code` e o link de verificação.
3. Autorize no GitHub; a página recarrega sozinha.
4. `/whoami` lista login e papéis. Sair revoga a sessão.

O token GitHub não é gravado. A sessão Forge vai num cookie HttpOnly, SameSite=Strict, Path=/, prazo padrão 8 h.

## Troubleshooting

| Sintoma | O que fazer |
| --- | --- |
| `Bind for 0.0.0.0:5433 failed` / porta em uso | Outro Postgres (compose de dev). `down` nele ou `FORGE_PG_HOST_PORT` |
| `forge-init: segredo ausente/vazio` | Defina as três senhas no ambiente **antes** do primeiro `up` (volume novo) |
| `forge-web: segredo ausente` | O backend não leu `/run/secrets/...`; conferir `secrets:` no compose |
| `host_rejected` | Host fora da allowlist. Padrão: 127.0.0.1/localhost nas portas 8090 e 8091 |
| `csrf` | Recarregue a página e tente de novo (cookie `forge_csrf` + cabeçalho/campo) |
| `forbidden` em operação futura de tarefa | Falta papel `editor` (owner sozinho não basta) |
| `device_flow_disabled` | Habilite Device Flow no OAuth App |
| Volume antigo, senha nova ignorada | A senha do papel já está no PGDATA; `ALTER ROLE` |

## O que vem no PR B

`forge_frontend`: nginx em `127.0.0.1:8090`, arquivos estáticos, `/api/` → `forge_backend`. Cookie de sessão permanece Path=/ (mesma origem). CSRF: cookie legível + `X-CSRF-Token`. Ligar `FORGE_TRUST_FORWARDED` só para o IP do frontend na rede compose. A publicação 8091 do backend pode ser retirada quando o proxy existir.
