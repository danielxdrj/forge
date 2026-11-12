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
| `FORGE_FRONTEND_HOST_PORT` | origem do navegador (padrão `8090`). O compose interpola essa porta em `FORGE_WEB_HOSTS`. Se você definir `FORGE_WEB_HOSTS` à mão, inclua `127.0.0.1:<porta>` e `localhost:<porta>` |
| `FORGE_SESSION_TTL_SECONDS` | prazo da sessão web/CLI (padrão 7 dias; mínimo 60, máximo 604800) |
| `FORGE_CURSOR_MODEL` | opcional; modelo da assinatura Cursor (sem default de custo) |
| `FORGE_CONNECTIONS_KEY` | chave Fernet da área Conexões (opcional). Sem ela o painel sobe, mas `/conexoes` fica desligada |
| `FORGE_OBSIDIAN_VAULT` | caminho **dentro do container** do vault Obsidian (ex.: `/vault`). Sem isto, ou sem allowlist, a Teia mostra o vault desligado; notas manuais e o restante do painel seguem |
| `FORGE_OBSIDIAN_ALLOW` | pastas relativas permitidas, separadas por vírgula (ex.: `Forge,Projetos`). Sem ela o vault fica desligado |
| `FORGE_GRAPH_DIR` | diretório dos `graph.json` no container (padrão `/graphs`, volume `forge_graphs`) |
| `FORGE_GRAPH_POLL_SECONDS` | intervalo do poll de releases (padrão `3600`; `0` desliga o loop e mantém só o passo na subida) |

A senha **não** vai para arquivo no repositório. O Postgres lê `secrets.environment`. O `forge_backend` é `read_only: true`; Compose v2 recusa `secrets.environment` nesse caso (`file is the sole supported option`). **Plano B:** tmpfs em `/run/secrets` (mode 0700, uid/gid 1000); o entrypoint grava as senhas da env em arquivos 0600 nesse tmpfs e remove as variáveis do processo antes do uvicorn. O código continua lendo de arquivo. Residual: `docker inspect` ainda mostra a env configurada no serviço. Ainda precisa ser validado no Windows (Docker Desktop).

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
# opcional, área Conexões: $env:FORGE_CONNECTIONS_KEY = (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
Set-Location <CAMINHO_DO_REPO>
docker compose -f docker-compose.forge.yml up -d --build
```

Bash equivalente: exporte as mesmas variáveis e rode o `docker compose`.

## Login gh e Cursor CLI (dentro do container, como usuário `forge`)

As ferramentas estão **na imagem**. Credenciais ficam no volume `forge_cli_home` (`HOME` do usuário `forge`, uid 1000). Não monte keyring, `HOME`/`APPDATA` nem `docker.sock` do Windows. **Não** use `docker compose exec -u 0`: `gh`, `cursor-agent` e `python -m forge_core.auth.cli` correm como `forge`.

```powershell
docker compose -f docker-compose.forge.yml exec forge_backend gh auth login -s project
# se o login já existir sem o escopo:
docker compose -f docker-compose.forge.yml exec forge_backend gh auth refresh -s project
docker compose -f docker-compose.forge.yml exec forge_backend cursor-agent login
```

Siga o device flow que o comando mostrar. Sem `GH_TOKEN` / `GITHUB_TOKEN`. O `gh` grava o token **em texto puro** no volume `forge_cli_home`. Risco aceito: é um volume Docker próprio desta instalação. **Nunca** monte o keyring, `HOME` ou `%APPDATA%` do host.

A sessão Forge (web e `python -m forge_core.auth.cli`) também vive nesse volume (`/home/forge/.config/forge/session`, permissão 0600, só o token de sessão do Forge — sem token GitHub). Logout web ou `python -m forge_core.auth.cli logout` invalida a sessão no banco e apaga o arquivo. Restart do container **não** pede login de novo enquanto a sessão valer (padrão 7 dias).

Se um volume antigo `forge_cli_home` estiver com dono root: uma vez, `docker compose -f docker-compose.forge.yml exec -u 0 forge_backend chown -R forge:forge /home/forge`. Volume **novo** já nasce com uid 1000.

## Bootstrap do owner e papel editor

O owner **não** implica editor. Quem vai criar tarefas precisa dos dois. O device flow da CLI corre no `bootstrap` e no primeiro `whoami`/`grant`; os comandos seguintes reusam o arquivo de sessão no volume. O id tem de ser o da conta que autorizar. **Não** informe `FORGE_DATABASE_URL` nem senha neste `exec`:

```powershell
docker compose -f docker-compose.forge.yml exec forge_backend python -m forge_core.auth.cli bootstrap --expect-github-id <ID_NUMERICO>
docker compose -f docker-compose.forge.yml exec forge_backend python -m forge_core.auth.cli grant --github-id <ID_NUMERICO> --role editor
```

## Abrir o painel e criar uma tarefa

```powershell
Start-Process 'http://127.0.0.1:8090'
```

1. **Entrar com GitHub**: a página mostra o `user_code` e o link de verificação. Autorize no GitHub; a página consulta `/api` sozinha.
2. `/api/auth/whoami` (via UI) lista login e papéis (pills na barra superior). Sem `editor`, a tela de tarefas explica que o owner não basta. A barra esquerda troca Tarefas, Investigação (notas manuais por issue), Teia de contexto (vault Obsidian + grafos) e, só para o papel **owner**, Conexões.
3. **Nova tarefa**: escolha um repositório da allowlist (org `ferreiraeborzone`), cole o contexto escrito (máx. 64 KiB; sem imagem) e **Gerar rascunho**.
4. Confira a pré-visualização. Comportamento esperado e Critérios de aceite vêm preenchidos mesmo com contexto curto, com prefixo `_Sugestão (revise):_` quando forem inferência. Só Objetivo pode ficar `[PENDENTE]`, e só se o contexto estiver vazio. Edite o corpo na própria prévia (textarea) ou complemente o contexto e **Gerar de novo**. Tipo, prioridade e size vêm sugeridos pelo gerador (opções do board IT Backlog, projeto 13); troque só se quiser. Se `/api/board/fields` falhar (ex.: gh sem escopo `project`), a tela mostra o erro real, não selects vazios.
5. **Confirmar e publicar**: o backend recusa se o `preview_hash` mudou (`409 diff_changed`) ou se ainda houver `[PENDENTE]` real (`400 pending_fields`). Sugestões `_Sugestão (revise):_` não bloqueiam. Issue, item do board e branch entram em `task_links`. Se falhar no meio, **Confirmar** de novo retoma; não duplica a issue.
6. A lista tem duas visões: **Publicadas** (com link da issue, nova aba) e **Rascunhos** (nunca publicados). **Descartar** um rascunho faz `POST /api/tasks/{id}/discard` (CSRF + editor), muda o status para `cancelado` sem apagar e registra no `audit_log`. Rascunhos cancelados saem da visão padrão.

O token GitHub não é gravado. A sessão Forge vai num cookie HttpOnly, SameSite=Strict, Path=/, prazo padrão 7 dias (renovação deslizante) e na tabela `sessions` (`token_hash`). CSRF: cookie legível `forge_csrf` + cabeçalho `X-CSRF-Token` em todo não-GET. Sem script inline (CSP `default-src 'self'`).

## Vault Obsidian e grafos Graphify

Notas manuais da aba **Investigação** ficam no Postgres do Forge (`investigation_notes`). Não dependem do vault. Editor ou owner cria/edita/apaga; o `audit_log` registra só `note:{id}` e `bytes=N`, nunca o corpo.

O vault Obsidian é opcional. Sem `FORGE_OBSIDIAN_VAULT` ou sem `FORGE_OBSIDIAN_ALLOW`, `/api/vault` e a aba Teia mostram **desligado**; o resto do painel continua.

### Bind mount no Windows (caminho de exemplo)

O vault **inteiro** entra somente leitura em `/vault`. Só a pasta `Forge/` é remontada por cima com escrita (o helper de escrita da fase 2 recusa qualquer outro destino). **Não** monte o keyring, `HOME`/`APPDATA` nem `docker.sock`.

O caminho real no Windows ainda não está fechado. Exemplo para descomentar em `docker-compose.forge.yml` e ajustar:

```yaml
# - "C:/Users/<USER>/Documents/ObsidianVault:/vault:ro"
# - "C:/Users/<USER>/Documents/ObsidianVault/Forge:/vault/Forge"
```

```powershell
$env:FORGE_OBSIDIAN_VAULT = '/vault'
$env:FORGE_OBSIDIAN_ALLOW = 'Forge,Projetos'
```

A API lista e lê `.md` só dentro da allowlist: `realpath`, sem seguir symlink para fora, com teto de tamanho e de quantidade. O log guarda caminho relativo e hash, nunca o texto. Escrita só em `Forge/` (notas de issues concluídas em `Forge/<repo>/<número>.md`): nome sanitizado, pastas intermediárias só sob `Forge/`, arquivo temporário + `replace`.

### Volume `forge_graphs` e poll de release

O backend instala `graphifyy==0.9.106` (comando `graphify`) e roda só `graphify extract <clone> --code-only` com `GRAPHIFY_BACKEND=none` (offline, sem chave, sem LLM). A saída (`graph.json` + metadados: tag, commit, data, nós/arestas) vai ao volume `forge_graphs` montado em `/graphs`.

Na subida e a cada `FORGE_GRAPH_POLL_SECONDS` (padrão 1 h), o backend consulta a tag de release mais recente de cada um dos 5 repositórios ativos da allowlist via `gh` da sessão já logada no volume `forge_cli_home`. **Não** há `GH_TOKEN` / `GITHUB_TOKEN` no compose nem nos logs. Se a tag mudou, reclona e reindexa. Um lock impede duas corridas juntas. O papel **owner** tem o botão **Atualizar grafo** (`POST /api/graphs/refresh`, CSRF + `audit_log`). Editor ou owner lê o status e consulta nós em `/api/graphs*`. O front não fala com o Graphify nem com o disco.

O mesmo poll também importa issues **fechadas** e as que estão na coluna Done do board IT Backlog (projeto 13), só dos 5 repositórios da allowlist. A leitura é `gh` na sessão já logada: `issue list/view`, `pr view` e GraphQL. **Não** cria nem edita issue, PR ou item do board. O corpo passa por redação (tokens `ghp_`/`gho_`/`github_pat_`, chaves AWS, JWT, `password=`/`senha:`/`token=`, connection string com credencial, chave privada) **antes** de gravar. Upsert em Postgres por `repo+number` (reimportar atualiza). Sem vault, o registro vive só no banco. Com `FORGE_OBSIDIAN_VAULT` e pasta `Forge/` gravável, cada issue vira `Forge/<repo>/<número>.md` (helper atômico, `realpath`, sem symlink). O papel **owner** tem o botão **Importar issues concluídas** na Investigação (`POST /api/completed-issues/import`, CSRF + `audit_log` com contagens, sem corpo). Editor ou owner lê semelhantes em `GET /api/completed-issues?issue=owner/repo#n`. O rascunho de tarefa cita as top 5 no markdown e no prompt do modelo; notas do vault **não** entram no prompt.

### Riscos e mitigações

| Risco | Mitigação |
| --- | --- |
| Ler pastas do vault além da allowlist | `FORGE_OBSIDIAN_ALLOW` + `realpath` + recusa de symlink; sem allowlist a API fica desligada |
| Escrita fora de `Forge/` | overlay RW só nessa pasta; helper recusa nome com barra/`..` e grava atômico |
| Vazamento do corpo da nota | `audit_log` e logs só com id/tamanho ou path/hash; UI com `textContent` |
| Graphify chamar LLM ou rede | `GRAPHIFY_BACKEND=none` + `--code-only`; testes dublê de `gh`/`graphify`/rede |
| Token GitHub no ambiente | `gh` usa a sessão do volume; `GH_TOKEN`/`GITHUB_TOKEN` fora do compose e do filtro de env |
| Segredo no corpo da issue importada | redação antes de gravar/usar; `audit_log` e logs só com repo/número/bytes/hash |
| Importador escrever no GitHub | só comandos de leitura (`issue list/view`, `pr view`, GraphQL query); testes recusam create/edit |
| Volume de grafo no rootfs read-only | named volume `forge_graphs` em `/graphs` (uid 1000 na imagem) |
| Montar demais do host | proibido keyring, `HOME`/`APPDATA`, `docker.sock` |

## Área Conexões (`/conexoes`)

Cadastro de MySQL, Postgres, FTP, SFTP e Portainer, com vários hosts por conexão (rótulo + ordem; um host preferido). Só o papel **owner** cria, edita ou apaga. **Editor** (ou owner) lista e testa. O teste tenta o host preferido e depois os demais, ~5 s cada, e diz qual funcionou ou por que cada um falhou. O front só chama `/api/connections*`; o segredo nunca volta na API (`secret_set: true/false`) e a tela só permite substituí-lo.

### Gerar a chave

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Bash: o mesmo comando. Guarde o valor fora do Git. Nome da variável: **`FORGE_CONNECTIONS_KEY`**. No container o entrypoint grava `/run/secrets/forge_connections_key` (0600 no tmpfs) e **remove a variável do processo**. O backend lê só `FORGE_SECRET_CONNECTIONS_KEY_FILE` (caminho), nunca um arquivo de config do repositório. Sem chave, a área informa que está desligada; o resto do painel continua no ar.

No compose, a chave é opcional (`${FORGE_CONNECTIONS_KEY:-}`). Defina-a no ambiente **antes** do `up`, como as senhas do Postgres. O `forge_backend` continua `read_only` + tmpfs `/run/secrets` (plano B); não use `secrets.file` nem monte o keyring/`HOME`/`docker.sock`.

### Rotação

1. Gere uma chave nova (comando acima).
2. Recadastre o segredo de **cada** conexão na tela (a chave antiga não descriptografa o ciphertext anterior).
3. Exporte `FORGE_CONNECTIONS_KEY` com o valor novo e recrie o `forge_backend` (`up -d --force-recreate forge_backend`). A senha do Postgres no volume **não** muda com isso.
4. Não deixe a chave antiga nem a nova em arquivo versionado, log ou dump publicado.

O ciphertext em `connections.secret_ciphertext` é Fernet. `forge_readonly` pode SELECT nessa coluna (é cifrada); não vê o valor em claro. A API e o `audit_log` não gravam o segredo.

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
SELECT repo, number, title, closed_at, url, imported_at FROM completed_issues ORDER BY repo, number;
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
| `forge-web: segredo ausente` | O entrypoint não materializou `/run/secrets` a partir da env; conferir tmpfs `/run/secrets` e as variáveis `FORGE_PG_*_PASSWORD` |
| Conexões desligada / `vault_disabled` | Falta `FORGE_CONNECTIONS_KEY` no ambiente do compose; gerar Fernet (comando acima), exportar e recriar o `forge_backend` |
| Teia / vault Obsidian desligado | Falta `FORGE_OBSIDIAN_VAULT` ou `FORGE_OBSIDIAN_ALLOW`, ou o bind mount não está em `/vault`. Notas manuais em Investigação continuam |
| Grafo `not_indexed` / `no_release` | Ainda não houve extract, ou o repo não tem release. Owner: **Atualizar grafo**. Confira `gh auth status` no container |
| Investigação sem issues concluídas | Owner: **Importar issues concluídas** (ou esperar o poll). Confira `gh auth status` no container. Sem vault, o registro fica só no Postgres |
| `vault_invalid` | A chave não é Fernet (32 bytes em Base64 URL). Gere outra e recadastre os segredos das conexões |
| `forbidden` em salvar conexão | Falta papel `owner`. Listar/testar exige `editor` ou `owner` |
| `forge-auth: FORGE_DATABASE_URL é obrigatória` | Comando rodou **fora** do container. Dentro, os arquivos de segredo preenchem a URL |
| `host_rejected` | Host fora da allowlist. Se mudou `FORGE_FRONTEND_HOST_PORT`, o compose já interpola em `FORGE_WEB_HOSTS`; se você definiu `FORGE_WEB_HOSTS` à mão, inclua a porta nova |
| `csrf` | Recarregue a página e tente de novo (cookie `forge_csrf` + cabeçalho `X-CSRF-Token`) |
| `forbidden` ao gerar/confirmar | Falta papel `editor` (owner sozinho não basta) |
| `diff_changed` | A pré-visualização mudou; salve o rascunho e confirme de novo |
| `pending_fields` | Ainda há `[PENDENTE]` nas seções listadas no JSON `fields`; edite o corpo ou complemente o contexto |
| `project_scope` | `gh auth login -s project` ou `gh auth refresh -s project` dentro do container |
| `cannot create secret ... file is the sole supported option` | Compose recusou `secrets.environment` em serviço `read_only`. Este repositório usa o plano B (tmpfs `/run/secrets` + entrypoint); atualize a imagem e `up` de novo |
| `exec /entrypoint.sh: no such file or directory` / initdb sem papéis | Scripts com CRLF (`core.autocrlf=true`). `git add --renormalize .` ou reclonar; `.gitattributes` força LF em `*.sh`, `*.conf` e `Dockerfile*` |
| Selects de tipo/prioridade/size vazios | `/api/board/fields` falhou; a tela mostra o erro (quase sempre escopo `project` do gh) |
| `device_flow_disabled` | Habilite Device Flow no OAuth App |
| Página em 8091 recusada / conexão recusada | A 8091 do backend **não** é publicada. Use `http://127.0.0.1:8090` |
| `gh` / `cursor-agent` sem permissão em `/home/forge` | Volume antigo como root: `chown` uma vez como uid 0 (passo acima) |
| Volume antigo, senha nova ignorada | A senha do papel já está no PGDATA; `ALTER ROLE` |
