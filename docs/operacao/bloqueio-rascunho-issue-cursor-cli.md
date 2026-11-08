# Bloqueio: rascunho de issue via CLI headless do Cursor

Estado: **parado sem implementação** (revalidado após a mudança de escopo de 08/11/2026 ~03:05). A tarefa pede um adaptador LLM cuja invocação seja **garantida** sem ferramentas, sem escrita e sem acesso a repositório. A documentação oficial da Cursor CLI **não oferece essa fronteira**. Sem essa decisão, o gerador e a criação remota **não entram no código**.

A mudança de escopo **substitui só** “`gh` apenas texto”: quando o fluxo existir, a CLI local do **usuário** (não deste agente) cria issue real. Isso **não** remove o bloqueio do motor. Implementar `gh` agora, com gerador inventado ou Cursor sem fronteira, seria falsa garantia.

Não foi enviado subprocesso Cursor, não foi ligado `--force`/`--trust`/`--yolo`, **não foi criada issue/branch/projeto/PR da empresa por nós**, não houve teste de rede, não foi aberto serviço on-demand e a versão do produto não muda.

A autenticação humana do Forge (v0.16.0, PR #26) não é reaberta. O login real Windows/SQLite já validado pelo usuário (`danielxdrj`, `gh:138545463`, owner) não foi repetido.

## O que a tarefa exigia do motor

- Interface única; primeiro adaptador = CLI headless do Cursor; Claude Code só por troca futura de configuração.
- Chamada recebe **apenas** contexto do usuário e o template; sem credenciais Forge/GitHub/banco, sem outras env, sem arquivos do host, sem metadados de repo.
- Reusar o login próprio da Cursor CLI (armazenamento dela) ou variável de sessão específica; config só caminhos/opções, não segredos.
- Não presumir que um prompt “não use tools” isola.
- Não habilitar trust, force ou bypass.
- Se a CLI não oferecer fronteira real, **parar e reportar** em vez de falsa garantia ou fallback mais arriscado.

## Fontes oficiais (consultadas)

| Fonte | URL |
| --- | --- |
| Parâmetros | https://cursor.com/docs/cli/reference/parameters |
| Headless | https://cursor.com/docs/cli/headless |
| Uso do Agent na CLI | https://cursor.com/docs/cli/using |
| Autenticação | https://cursor.com/docs/cli/reference/authentication |
| Instalação | https://cursor.com/docs/cli/installation |
| Staff Cursor sobre modo locked-down | https://forum.cursor.com/t/cursor-cli-a-locked-down-headless-mode-file-tools-only-no-hooks-mcp-plugins-enforced-tool-allowlist/173496 |
| Staff Cursor sobre `--mode ask` | https://forum.cursor.com/t/cursor-cli-limitations/152089 |

Nesta máquina de implementação o binário `agent` / `cursor-agent` **não estava instalado**. O `--help` local não pôde ser executado. A invocação foi conferida só pela documentação oficial e pelo fórum citado, sem login e sem chamada paga. A página de parâmetros foi relida depois da mudança de escopo: `-p` continua documentado com *all tools, including write and shell*.

## O que a CLI documenta hoje

1. **`--print` / `-p` tem todas as ferramentas.** A tabela de parâmetros diz literalmente: *“Print responses to console (for scripts or non-interactive use). Has access to all tools, including write and shell.”*
2. **Modo não interativo tem escrita plena.** A página de uso: *“Cursor has full write access in non-interactive mode.”*
3. **Sem `--force`, a alteração pode não ser aplicada, mas as tools continuam existindo.** Headless: sem `--force` as mudanças são *propostas*; com `--force`/`--yolo` são aplicadas. Isso não é “sem ferramentas”. A tarefa proíbe `--force`.
4. **`--mode=ask` não elimina tools nem acesso a repo.** Ask “explora o código sem fazer mudanças” e “pesquisa o codebase”. Staff (fev/2026): *“`--mode ask` … works read only … It may still use some tools like for reading code.”*
5. **Prompt não isola.** A própria página de uso recomenda *“do not write any code”* para reduzir edições — o mesmo tipo de instrução que a tarefa recusa como garantia.
6. **Workspace padrão é o diretório atual** (em geral o repositório de quem opera). `--workspace` aponta um root; `--worktree` cria worktree Git do projeto. Não há modo documentado “sem filesystem / sem repo”.
7. **MCP e regras do projeto carregam automaticamente** (`mcp.json`, `.cursor/rules`, `AGENTS.md`). `--approve-mcps` e `--trust` ampliariam isso; a tarefa os proíbe, mas **não há flag documentada que desligue todas as tools**.
8. **Sandbox da CLI não é “sem tools”.** `--sandbox enabled|disabled` e `agent sandbox …` regulam execução de *comandos* no sandbox da CLI, não um complete só-texto. Abrir sandbox de rede de containers do Forge continua negado (ADR-013); esta chamada local foi a única exceção candidata, e ela falhou no critério de fronteira.
9. **Flags internas `--allowed-tools` / `--exclude-tools`** aparecem em relato de fórum como *internal only*. Staff: modo headless documentado que limite tools, mantenha política da equipe e permita inspecionar o perfil **não está disponível**. Não usar flag oculta como garantia.
10. **Login.** Oficial: `agent login` (credencial guardada localmente pela CLI) ou `CURSOR_API_KEY` / `--api-key` (chave de dashboard, típica de automação/CI). A tarefa permite o login da CLI ou env de sessão; **não** pede chave nova nem on-demand. Não foi feito login real da Cursor CLI neste trabalho.

## Caminhos considerados e por que não foram adotados

| Caminho | Motivo da recusa |
| --- | --- |
| `agent -p --mode ask` + prompt “sem tools” | Ask ainda lê código; prompt não é fronteira; `--print` declara write e shell. |
| Workspace vazio + `--print` sem `--force` | Default/cwd ainda é escolhível; tools existem; leitura fora do workspace é relatada no fórum, sem garantia oficial em contrário. |
| `--sandbox enabled` | Sandbox de shell, não ausência de tools. |
| Detectar `tool_call` em `stream-json` e matar o processo | Staff no fórum: pode ser *detect-and-abort*, não prevenção; o evento pode chegar depois da tool. Falsa garantia. |
| TypeScript SDK com `disallowedTools` | Serviço/API diferente da CLI aprovada; não estava no recorte; custo/contrato novos. |
| `CURSOR_API_KEY` / modelo on-demand | Custo e credencial novos, fora do pedido. |
| Inventar gerador sem LLM (só `[PENDENTE]`) | Troca silenciosa do motor aprovado. |
| Chamar a CLI mesmo assim “porque o usuário aprovou o Cursor” | Aprovação era do **adaptador**, condicionada à fronteira. Sem fronteira, a instrução é parar. |

## Instalação Windows (fatos e incertezas)

Documentado:

```powershell
irm 'https://cursor.com/install?win32=true' | iex
agent --version
agent login
```

- Linux/macOS/WSL: `curl https://cursor.com/install -fsS | bash`.
- PATH pós-instalação: a doc fala em `~/.local/bin` (Unix). No Windows nativo o local exato do binário **não está detalhado** na mesma página; não inventar compatibilidade.
- Auto-update da CLI é o padrão documentado; a versão efetiva na máquina do operador não foi medida aqui.
- Comportamento de `agent login` no Windows nativo (navegador, `NO_OPEN_BROWSER=1`, armazenamento) segue a página de autenticação; **não foi testado neste PR.**

O fluxo Forge já validado pelo usuário (login GitHub device flow, SQLite, Python 3.11+, venv) permanece o de `docs/operacao/autenticacao-humana.md`. Client ID OAuth é público. Variáveis Forge continuam só de sessão. **Nenhum comando `forge-tasks draft` foi adicionado.**

## Contrato aprovado e ainda não implementado (criação remota pelo usuário)

Quando o motor for desbloqueado, um PR seguinte deve cumprir isto. **Não está no código deste PR.**

Fluxo: gerar rascunho (template exato, sem seção Escopo no corpo, faltantes `[PENDENTE]`) → mostrar a issue completa → confirmar `s`/`N` (não interativo recusa sem `--yes`; `--yes` explícito pula o prompt e **não** contorna pendência, papel, escopo GitHub nem schema) → só então o processo local chama o `gh` do usuário.

`gh` local, sessão já no keyring do operador. Não coletar, copiar, gravar nem enviar token. Não fazer `gh auth login` / `gh auth refresh` por nós. Testes só com `gh` falso, sem rede. Env do subprocesso: o mínimo da autenticação nativa do `gh`; nada disso vai ao payload do Cursor/LLM nem por stdin do modelo. Subprocesso sem shell; quoting seguro. Texto do LLM é dado, nunca comando.

Pré-validar (papel `editor` revalidado na escrita, sem lock de banco atravessando rede; repo-alvo; título Conventional Commits; template; pendências obrigatórias; `gh` autenticado; escopo `project`; schema real do board) **antes** da primeira criação, para não deixar issue órfã evitável.

Se qualquer campo **obrigatório** abaixo tiver `[PENDENTE]`, bloquear **todas** as escritas remotas e pedir preenchimento. Metadados entram por opções da CLI, sem inferir.

### Campos obrigatórios (contrato; IDs de board não hardcodados)

Obrigatórios para escrita remota:

| Campo | Origem permitida | Não fazer |
| --- | --- | --- |
| Título Conventional Commits | LLM validado ou opção CLI | Aceitar título inválido ou placeholder como fato |
| Corpo nas seções do template, na ordem | LLM + validação determinística | Seção Escopo no corpo; inventar solicitante/prazo/regras |
| Repo-alvo `owner/repo` | Argumento do usuário | Inferir do cwd se o argumento faltar |
| Assignee | Fixo aprovado: `danielxdrj` | Outro assignee |
| Board | Org `ferreiraeborzone`, projeto **IT Backlog**, `projects/13` | Inventar project number |
| Sprint | Semana **atual** resolvida no **schema real** (`gh project field-list` / item-edit) | Número de sprint chutado |
| Tipo, Prioridade, Size | Opções CLI do usuário casadas às opções **reais** do campo | Inferir Size=3 etc. |
| Escopo | Só campo de board se o schema **já** tiver esse campo | Criar seção Escopo no corpo; ampliar schema |

Faltante no corpo ou opção de board sem match → `[PENDENTE]` / erro claro, sem `gh issue create`.

`--project` do `gh issue create` usa **título** do projeto, não preenche Sprint/Tipo/Prioridade/Size. Esses campos exigem `gh project item-add` / `gh project item-edit` com IDs obtidos na hora. Se faltar escopo: falhar e **mostrar** `gh auth refresh -s project` para o usuário rodar; não executar refresh.

Branch: `gh issue develop` ligado à issue. Convenção já no Core (ADR-012): `settings.branch_prefix` do repositório cadastrado, se existir, prefixa; o restante segue o padrão número-slug do `gh issue develop`. Não inventar outro padrão neste PR. FRG-21 ainda não existe no código.

Falha parcial: não duplicar issue/branch no retry; gravar na tarefa Forge número, URL e branch já obtidos; audit sem segredos; **não** apagar remoto por conta própria. Confirmação deve listar destino, repos, board e mutações.

## Runbook PowerShell (pré-requisitos do operador; Forge ainda não cria)

Os comandos Forge abaixo **não existem** até o motor ser desbloqueado. O operador pode deixar o `gh` pronto.

```powershell
# Python 3.11+ e venv (Forge auth v0.16.0, já validado pelo usuário — não repetir bootstrap se o dono já existe)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:FORGE_CONFIG_DIR = "<CAMINHO>"
$env:FORGE_DATABASE_URL = "sqlite:///<CAMINHO>\forge.db"
$env:FORGE_GITHUB_CLIENT_ID = "<CLIENT_ID_PUBLICO>"   # só sessão; não commitar

# GitHub CLI do usuário (keyring nativo; este agente não loga)
gh auth status
# Se projects/13 falhar por escopo, o operador (não o Forge) roda:
#   gh auth refresh -s project

# Quando o comando existir (ainda não):
#   python -m forge_core.tasks.draft --repo ferreiraeborzone/<repo> --context "..."
#   (mostra issue completa; s/N; sem --yes em pipe recusa)
#   python -m forge_core.tasks.draft ... --yes
#     # --yes não ignora [PENDENTE], papel editor, schema nem escopo project
```

Incertezas Windows: caminho do `gh.exe` e do `agent` nativo não foram medidos aqui; WSL vs nativo não foi declarado compatível sem evidência.

## O que não foi feito (de propósito)

- CLI `forge-tasks draft`, persistência via `TaskService`, arquivo markdown.
- Adaptador `ProviderAdapter` apontando para subprocesso Cursor.
- Qualquer `gh issue create` / `project item-add` / `issue develop` real (por nós ou em teste de rede).
- Leitura ou exibição de credencial Cursor/GitHub/Forge.
- Merge, tag, release ou bump de versão.

## Decisão que desbloqueia

Precisa de **uma** destas, explícita, **antes** de código de gerador ou de `gh`:

1. A Cursor CLI passa a documentar (e o operador confirma no `--help` da versão instalada) um modo **sem tools e sem workspace/repo**, sem `--trust`/`--force`; ou
2. O responsável aceita por escrito um isolamento **mais fraco** (ex.: ask + cwd vazio), com o risco de leitura/tools; ou
3. Outro motor só-texto, já existente na máquina, sem tools e sem custo on-demand novo, for aprovado no lugar da CLI Cursor.

Enquanto isso, o recorte de rascunho de issue **não entra no código**. A criação remota aprovada neste recorte espera o mesmo desbloqueio.
