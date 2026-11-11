# Resolver de issue (Windows / PowerShell)

Implementa uma issue num **clone temporário**, pede confirmação `s/N` e só então o Forge faz push e abre **PR em rascunho**. Não faz merge. Risco residual (ADR-016): não é sandbox de container (FRG-6); o motor roda na sua máquina.

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

Não grave token no Git. O subprocesso do motor **não** recebe `GH_TOKEN` / `FORGE_*` / `DATABASE_URL`.

## Diagnóstico (mesmo doctor do rascunho)

```powershell
python -m forge_core.draft doctor --model <MODELO_DA_ASSINATURA>
```

## Executar

Valida `owner/repo#n` e o modelo **antes** do login. Sem TTY e sem `--yes`, não publica.

```powershell
python -m forge_core.draft resolver ferreiraeborzone/<repo>#<n>
python -m forge_core.resolver ferreiraeborzone/<repo>#<n>
forge-tasks resolver ferreiraeborzone/<repo>#<n>
```

Confirmação: `s` ou `sim` (trim). Vazio, `n`, `nao` e `não` cancelam. Outra resposta: `Resposta inválida: responda s ou N. Cancelado.`

`--yes` pula só o prompt; ainda exige papel `editor` e a validação do diff.

```powershell
python -m forge_core.draft resolver ferreiraeborzone/<repo>#<n> --manter-clone
python -m forge_core.draft resolver --retomar <uuid-da-tarefa>
```

`--retomar` recupera repo, issue, clone, modelo e fase. Flags passadas de novo só sobrescrevem o que você informar.

O clone é apagado no fim, salvo `--manter-clone` ou se você retomar um diretório ainda no disco.

## O que o Forge faz depois do `s`

1. Commit Conventional Commits com referência à issue, se o motor não tiver commitado.
2. `git push` da branch (processo Forge, não o motor).
3. `gh pr create --draft` com `Closes #<n>` usando o `gh` da sua sessão.
4. Auditoria: identidade, hash do diff, modelo, repo/issue.

## Limites

- Sem container; `--trust` só no clone temporário desta execução.
- Motor sem `git push` e sem `gh` no env filtrado; risco residual se a CLI tentar tools.
- Diff recusado se tocar `.env`/chaves, `.git/config`/`hooks`, sair do clone, ou estourar teto de arquivos/linhas.
- Testes automatizados **não** chamam GitHub real nem LLM real.
