# Resolver de issue (Windows / PowerShell)

Implementa uma issue num **clone temporário**, pede confirmação `s/N` (sempre interativa) e só então o Forge commita, recoloca o `origin`, faz push e abre **PR em rascunho**. Não faz merge. Risco residual (ADR-016): Shell da CLI liberado; o processo corre com o seu utilizador; não é sandbox de container (FRG-6).

Compatibilidade Windows nativa **não foi medida neste repositório**. O login Forge já existente **não deve ser refeito** se o dono já existe.

Papel exigido: **`editor`**. Ter `owner` sozinho não basta.

## Pré-requisitos (você executa)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:FORGE_CONFIG_DIR = "<CAMINHO>"
$env:FORGE_DATABASE_URL = "sqlite:///<CAMINHO>\forge.db"
$env:FORGE_GITHUB_CLIENT_ID = "<CLIENT_ID_PUBLICO>"
$env:FORGE_CURSOR_MODEL = "<MODELO_DA_ASSINATURA>"
# Opcional: $env:FORGE_CURSOR_TIMEOUT = "600"
# Opcional: $env:FORGE_RESOLVER_ATTEMPTS = "1"

agent --version
agent login
gh auth status
```

Não grave token no Git. O subprocesso do motor **não** recebe `GH_TOKEN` / `FORGE_*` / `DATABASE_URL`. Git/gh do motor usam config vazia no temp (`GIT_CONFIG_GLOBAL`, `GH_CONFIG_DIR`); sem `SSH_AUTH_SOCK`. HOME/APPDATA podem ficar para o login da Cursor CLI.

## Diagnóstico (mesmo doctor do rascunho)

```powershell
python -m forge_core.draft doctor --model <MODELO_DA_ASSINATURA>
```

## Executar

Valida `owner/repo#n` e o modelo **antes** do login. Sem TTY, não publica — responda `s` ou `N` no terminal.

```powershell
python -m forge_core.draft resolver ferreiraeborzone/<repo>#<n>
python -m forge_core.resolver ferreiraeborzone/<repo>#<n>
forge-tasks resolver ferreiraeborzone/<repo>#<n>
```

Confirmação: `s` ou `sim` (trim). Vazio, `n`, `nao` e `não` cancelam. Outra resposta: `Resposta inválida: responda s ou N. Cancelado.` Não existe `--yes`.

```powershell
python -m forge_core.draft resolver ferreiraeborzone/<repo>#<n> --manter-clone
python -m forge_core.draft resolver --retomar <uuid-da-tarefa>
```

`--retomar` recupera repo, issue, clone, modelo, fase, URL do origin e hash do diff. Em fase `validated` o hash é conferido de novo. Flags passadas de novo só sobrescrevem o que você informar.

O clone é apagado no fim, salvo `--manter-clone` ou se você retomar um diretório ainda no disco. O `origin` só volta a existir no clone **depois** do `s`.

## O que o Forge faz depois do `s`

1. Recalcula o diff do working tree e compara com o hash da prévia (`diff_changed` se divergir).
2. Commit Conventional Commits com referência à issue (`--no-verify`, hooksPath vazio). Reconfere `.git`.
3. Recoloca o `origin` guardado no checkpoint e `git push origin HEAD:refs/heads/<branch>` (`--no-verify`).
4. `gh pr create --draft` com `Closes #<n>` usando o `gh` da sua sessão.
5. Auditoria: identidade, hash do diff, modelo, repo/issue.

## Limites

- Sem container; `--trust` só no clone temporário desta execução.
- Shell da CLI permanece permitido (testes no clone); git/gh isolados e sem `origin` durante o motor. Risco residual aceite (ADR-016).
- Diff recusado se tocar `.env`/chaves, `.gitattributes`/`.gitmodules`, `.git/config`/`hooks`, sair do clone, ou estourar teto. Mudança em `.git` após o snapshot → `git_meta_tampered`.
- `.cursor/cli.json` do Forge está em `.git/info/exclude` e não entra no commit.
- Testes automatizados **não** chamam GitHub real nem LLM real.
