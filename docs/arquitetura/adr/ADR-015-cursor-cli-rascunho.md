# ADR-015: rascunho de issue com Cursor CLI e gh local

- **Status:** Aceito (08/11/2026). O responsável aceitou o risco residual de ferramentas da Cursor CLI não serem 100% desligáveis.
- **Data:** 2026-11-08.
- **Relaciona:** ADR-003 (adaptador de provedor), ADR-007 (GitHub), ADR-010 (tarefa), ADR-012 (prefixo de branch), ADR-014 (papel editor).

## Contexto

O Forge precisa redigir um rascunho de issue a partir de contexto livre e, depois de confirmação humana, criar a issue no GitHub com o `gh` já autenticado na máquina de quem opera. A Cursor CLI foi escolhida como primeiro LLM. A documentação oficial **não garante** invocação sem ferramentas; `--print` declara acesso a write e shell.

## Decisão

- **D1. Isolamento aceito, não absoluto.** Cada chamada cria um diretório temporário **vazio** novo (`mkdtemp` com prefixo `forge-cursor-`), usa `--workspace` nesse diretório, `--mode ask`, `--print` / `--output-format text`, e um `.cursor/cli.json` do projeto com `permissions.deny` nos tokens **documentados** em https://cursor.com/docs/cli/reference/permissions (`Shell(*)`, `Shell(*:*)`, `Read(*)`, `Read(**/*)`, `Read(/**)`, equivalentes de `Write`, `WebFetch(*)`, `Mcp(*:*)`). Não se usa `Shell()` / `Read()` vazios (não há garantia de glob universal). Não se usa `--force`, `--yolo`, `-f`, `--approve-mcps`. O diretório é removido no `finally`.
- **D1b. `--trust` só no temp do Forge.** A Cursor CLI em pasta vazia pede Workspace Trust no Windows. `--trust` entra no argv **somente** quando o `cwd`/`--workspace` é o diretório que esta chamada criou e vai apagar. Não se passa `--trust` no repositório do operador nem em outro caminho. Risco: a flag dispensa o prompt de confiança **naquele** diretório efêmero; se a resolução do cwd falhar, o adaptador recusa a flag. Não amplia permissões de tool nem desliga o deny.
- **D1c. Executável no Windows e prompt via stdin.** `subprocess` com `shell=False` não acha `agent` se o instalador só publicou `agent.cmd`/`agent.ps1`. Resolução: `FORGE_CURSOR_AGENT` (se definido) > `shutil.which("agent")` (respeita `PATHEXT`) > `%LOCALAPPDATA%\cursor-agent\agent.cmd` se o arquivo existir. Erro `cursor_cli_missing` se nada for encontrado. O prompt **não** vai no argv: `.cmd` passa por `cmd.exe` (limite ~8191 caracteres; `& | ^ %` e aspas corrompem argumento). Com `-p` e prompt posicional vazio, a CLI (2026.11.10, `build-prompt.ts`) lê o stdin até EOF. Nenhum argumento controlado pelo usuário entra no argv.
- **D1d. Erro da CLI.** `cursor_cli_error` inclui código de saída e trecho de stderr (máx. 500 caracteres) depois de `redact()` e de mascarar valores de env sensíveis (`TOKEN`/`KEY`/…).
- **D2. Risco residual.** Deny + pasta vazia **não** são sandbox forte. A CLI pode ainda tentar tools. Isto foi aceito explicitamente. Não há garantia total.
- **D3. Interface única `ProviderAdapter.complete`.** Só contexto do usuário + instrução do template entram no prompt. Sem credencial Forge/GitHub/banco. Claude Code fica para troca futura de adaptador, não nesta entrega.
- **D4. Env allowlist.** O subprocesso Cursor recebe PATH, HOME/USERPROFILE/APPDATA (login nativo da CLI) e, se existirem, `CURSOR_API_KEY` / `CURSOR_AUTH_TOKEN` de sessão. Não recebe `GH_TOKEN`, `GITHUB_TOKEN`, `FORGE_*`, `DATABASE_URL`. O subprocesso `gh` (só depois da confirmação, no Forge) recebe allowlist própria, também sem esses tokens; usa o keyring nativo.
- **D5. gh só no Forge.** Preview + `s`/`N` (default N). `--yes` pula só o prompt. Qualquer `[PENDENTE]` em campo obrigatório bloqueia. Falha de project: mostrar `gh auth refresh -s project`, não executar. `gh issue create` devolve URL (sem `--json`). Sprint/opções: `gh api graphql` documentado (field-list não traz iterations). Assignee `danielxdrj`. Branch: `gh issue develop`.
- **D6. Sem transação banco+rede.** Checkpoint `*.md.forge-remote.json` + `--retomar <tarefa>`. Reconciliar com `gh issue view` antes de criar de novo. O Forge não apaga issue.

## Consequências

Testes usam Cursor e gh falsos. Nenhuma issue da empresa é criada por CI ou por agentes. Quem opera instala e autentica Cursor CLI e `gh` na própria máquina.
