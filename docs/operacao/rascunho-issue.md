# Rascunho de issue (Windows / PowerShell)

Compatibilidade Windows nativa **não foi medida neste repositório**. WSL e nativo podem diferir. O login Forge v0.16.0 em Windows/SQLite já foi validado pelo operador (`danielxdrj`, `gh:138545463`, owner) e **não deve ser refeito** se o dono já existe.

## Pré-requisitos (você executa)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:FORGE_CONFIG_DIR = "<CAMINHO>"
$env:FORGE_DATABASE_URL = "sqlite:///<CAMINHO>\forge.db"
$env:FORGE_GITHUB_CLIENT_ID = "<CLIENT_ID_PUBLICO>"   # só nesta sessão
# FORGE_CURSOR_AGENT só se `agent`/`agent.cmd` não estiver no PATH nem em
# %LOCALAPPDATA%\cursor-agent\agent.cmd. Na maioria dos installs Windows isso não é preciso.
# Modelo explícito da SUA assinatura Cursor. Confira em `agent models` o que o plano cobre.
# Não há garantia de custo zero. Não ligue on-demand / yolo / force.
$env:FORGE_CURSOR_MODEL = "<MODELO_DA_ASSINATURA>"

irm 'https://cursor.com/install?win32=true' | iex
agent --version
agent login
agent models
gh auth status
# Se o board falhar por escopo project, VOCÊ roda (o Forge não roda):
#   gh auth refresh -s project
```

OAuth Client ID é o público já usado no login Forge. Não grave token no Git.

## Diagnóstico Cursor CLI (`doctor`)

Não exige `FORGE_DATABASE_URL`. Mostra caminho do `agent`, `agent --version`, **nomes** das variáveis repassadas (nunca valores), scratch TMP, `NODE_OPTIONS` injetado, `model=` (flag `--model` > `FORGE_CURSOR_MODEL` > padrão da CLI) e uma chamada mínima (`responda OK`) pelo **mesmo** resolvedor de modelo do `draft`.

```powershell
$env:FORGE_CURSOR_MODEL = "<MODELO_DA_ASSINATURA>"
python -m forge_core.draft doctor
python -m forge_core.draft doctor --model composer-2.5
# ou:
forge-tasks doctor
```

## Isolar no PowerShell (env completo vs. mínimo)

Pasta temp vazia, prompt via stdin, `--trust` só nessa pasta. Compare a sessão normal com um env mínimo (ajuste o caminho do `agent.cmd`):

```powershell
$ws = Join-Path $env:TEMP ("forge-manual-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $ws | Out-Null
$agent = (Get-Command agent -ErrorAction SilentlyContinue).Source
if (-not $agent) { $agent = Join-Path $env:LOCALAPPDATA "cursor-agent\agent.cmd" }

# A) env da sessão (completo)
"responda OK" | & $agent -p --output-format text --mode ask --workspace $ws --trust
Write-Host "exit A:" $LASTEXITCODE

# B) env mínimo (allowlist Windows + NODE_OPTIONS do Forge; sem GH_TOKEN/FORGE_*)
$scratch = Join-Path $env:TEMP ("forge-scratch-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $scratch | Out-Null
$env:TMP = $scratch
$env:TEMP = $scratch
$env:NODE_OPTIONS = "--max-old-space-size=512"
Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:FORGE_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
"responda OK" | & $agent -p --output-format text --mode ask --workspace $ws --trust
Write-Host "exit B:" $LASTEXITCODE
Remove-Item -Recurse -Force $ws, $scratch -ErrorAction SilentlyContinue
```

Se A passa e B aborta (exit 134 / GCs V8), o env mínimo ainda está incompleto. Se os dois abortam, o problema não é o filtro do Forge.

## Gerar

`--contexto` e `--arquivo` são exclusivos. Posicional é alias de `--contexto`. `--arquivo -` lê stdin.

```powershell
python -m forge_core.draft draft --contexto "o relatorio X soma em dobro" --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3

python -m forge_core.draft draft --arquivo .\contexto.txt --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3

Get-Content .\contexto.txt -Raw | python -m forge_core.draft draft --arquivo - --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3

forge-tasks draft --contexto "..." --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3
```

A CLI mostra a issue, destino, board e pergunta `s/N` (default N). Confirmação: `s` ou `sim` (trim, sem diferenciar maiúsculas). Vazio, `n`, `nao` e `não` cancelam com `Cancelado.`; qualquer outra resposta (ex.: `ss`) cancela com `Resposta inválida: responda s ou N. Cancelado.`. Sem TTY e sem `--yes`, não publica. Anote o `tarefa <uuid>` impresso.

Se o markdown de `--output` já existir, o comando recusa `file_exists` **antes** de login, rede ou LLM. Quando houver sidecar `*.forge-draft.json`, a mensagem inclui `use --retomar <uuid>`.

`--yes` **não** ignora `[PENDENTE]` real (sugestões `_Sugestão (revise):_` não bloqueiam), papel `editor` nem escopo `project`. Comportamento esperado e Critérios de aceite são sempre inferidos; só Objetivo pode ficar `[PENDENTE]`, e só com contexto vazio.

## Retomar após falha parcial (mesmo markdown, sem novo LLM)

`--retomar <uuid>` não exige `--repo`. Repo, tipo, prioridade, size, output, sprint, escopo e prefixo de branch vêm do rascunho (`*.forge-draft.json` e o comentário na tarefa). Flags passadas de novo só sobrescrevem o que você informar. Se a issue já tiver sido criada, `--repo` diferente do checkpoint é recusado (`repo_mismatch`) para não misturar repositórios.

```powershell
python -m forge_core.draft draft --retomar <uuid-da-tarefa> --yes
python -m forge_core.draft draft --retomar <uuid-da-tarefa> --tipo Bug --yes
```

Não apague a issue no GitHub para “desfazer”. Se o remoto não bater com o checkpoint (`rascunho.md.forge-remote.json`), o comando falha sem criar outra issue.

## Próximos passos (não nesta entrega)

Print/anexo de imagem, OCR, Gmail e n8n: nova implementação de `ContextSource`, etapa própria.

## Limites

- Isolamento Cursor: pasta vazia + deny documentado + `--mode ask`. `--trust` **só** nesse diretório temporário (Workspace Trust headless). **Não é garantia total** (ADR-015).
- Prompt da CLI vai no stdin (`-p` sem prompt posicional), não no argv — evita `cmd.exe` / limite de ~8191 caracteres no Windows.
- Sprint vem de GraphQL (`gh api graphql` com sessão nativa), não de `gh project field-list`.
- `gh issue create` imprime URL; não usamos `--json` nesse comando.
- Testes não criam issue da empresa.
