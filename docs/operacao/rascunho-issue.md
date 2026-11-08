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
# opcional, modelo já incluído na sua conta Cursor (não ative on-demand):
$env:FORGE_CURSOR_MODEL = "composer-2.5"
$env:FORGE_CURSOR_AGENT = "agent"   # se o binário não estiver no PATH, coloque o caminho

# Cursor CLI (você instala e entra)
irm 'https://cursor.com/install?win32=true' | iex
agent --version
agent login
agent status

# GitHub CLI (você instala e entra; keyring nativo)
gh auth status
# Se o board falhar por escopo project, VOCÊ roda (o Forge não roda):
#   gh auth refresh -s project
```

OAuth Client ID é o público já usado no login Forge. Não grave token no Git.

## Gerar (login editor a cada comando)

```powershell
python -m forge_core.draft draft "o relatorio X soma em dobro" --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3
# ou: python -m forge_core.draft draft --file .\contexto.txt --repo ferreiraeborzone/<repo> ...
# ou: forge-tasks draft "..." --repo ferreiraeborzone/<repo> ...
```

(`forge-tasks draft` equivale depois do `pip install -e .`.)

A CLI mostra a issue completa, repo, board `ferreiraeborzone` / IT Backlog `projects/13`, assignee `danielxdrj` e pergunta `s/N` (default N). Sem TTY e sem `--yes`, publica nada; o markdown e a tarefa Forge já existem.

```powershell
python -m forge_core.draft draft "..." --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3 --yes
```

`--yes` **não** ignora `[PENDENTE]`, papel nem escopo `project`. Sprint = iteração da semana atual no schema, ou `--sprint "Semana NN"` se o nome existir. `--escopo` só preenche campo de board se o schema tiver Escopo.

Saída esperada após confirmar: número e URL da issue, nome da branch (`gh issue develop`), id da tarefa Forge. Arquivo markdown não é sobrescrito se já existir.

## Limites

- Isolamento Cursor: pasta vazia + deny documentado. **Não é garantia total** (ADR-015).
- Este repositório **não** cria issue da empresa em teste. Não extraímos tokens da Cursor CLI nem do `gh`.
