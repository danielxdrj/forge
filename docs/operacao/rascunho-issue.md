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

## Gerar

`--contexto` e `--arquivo` são exclusivos. Posicional é alias de `--contexto`. `--arquivo -` lê stdin.

```powershell
python -m forge_core.draft draft --contexto "o relatorio X soma em dobro" --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3

python -m forge_core.draft draft --arquivo .\contexto.txt --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3

Get-Content .\contexto.txt -Raw | python -m forge_core.draft draft --arquivo - --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3

forge-tasks draft --contexto "..." --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3
```

A CLI mostra a issue, destino, board e pergunta `s/N` (default N). Sem TTY e sem `--yes`, não publica. Anote o `tarefa <uuid>` impresso.

`--yes` **não** ignora `[PENDENTE]` (em qualquer campo obrigatório), papel `editor` nem escopo `project`.

## Retomar após falha parcial (mesmo markdown, sem novo LLM)

```powershell
python -m forge_core.draft draft --retomar <uuid-da-tarefa> --repo ferreiraeborzone/<repo> --output .\rascunho.md --tipo Bug --prioridade Alta --size 3 --yes
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
