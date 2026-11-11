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
- **D4. Env allowlist.** Comparação **case-insensitive** (Windows usa `SystemRoot`, não `SYSTEMROOT`). POSIX: PATH, HOME/USER/SHELL, TMPDIR, locale, XDG_*. Windows: PATH, PATHEXT, SystemRoot, SystemDrive, windir, ComSpec, ProgramData, ProgramFiles*, ALLUSERSPROFILE, APPDATA, LOCALAPPDATA, USERPROFILE, HOMEDRIVE/HOMEPATH, USERNAME, NUMBER_OF_PROCESSORS, PROCESSOR_ARCHITECTURE, OS, TMP/TEMP. Cursor (código da CLI 2026.11.10): só `CURSOR_API_KEY`, `CURSOR_AUTH_TOKEN`, `CURSOR_CONFIG_DIR`, `CURSOR_DATA_DIR`, `CURSOR_API_ENDPOINT` — não todo `CURSOR_*` (há `CURSOR_ASKPASS_SECRET`). Nunca `GH_TOKEN`, `GITHUB_TOKEN`, `GH_*` (exceto `GH_HOST` no subprocesso gh), `FORGE_*`, `DATABASE_URL`. `NODE_OPTIONS` do usuário **não** é copiado; o Forge injeta só `--max-old-space-size=<N>` (`FORGE_CURSOR_MAX_OLD_SPACE_MB`, default 512, lida pelo Forge, não repassada).
- **D4b. TMP fora do workspace.** `TMP`/`TEMP`/`TMPDIR` do sistema são preservados. Se faltarem, um `mkdtemp` `forge-cursor-scratch-*` **fora** do workspace com `--trust`. Não apontar TMP para o diretório confiado (a CLI escreve cache/log; deny do workspace não deve coincidir com o scratch do Node).
- **D4c. Stdin.** `Popen.communicate(prompt)` grava e fecha stdin (EOF). `build-prompt.ts` lê stdin uma vez até `end` quando `-p` e prompt posicional vazio; não há loop. Abort V8 (exit 134) pode ir para stdout: o erro usa stderr e, se vazio, um trecho de stdout, sempre redigido.
- **D5. gh só no Forge.** Preview + `s`/`N` (default N). `--yes` pula só o prompt. Qualquer `[PENDENTE]` em campo obrigatório bloqueia. Falha de project: mostrar `gh auth refresh -s project`, não executar. `gh issue create` devolve URL (sem `--json`). Sprint/opções: `gh api graphql` documentado (field-list não traz iterations). Assignee `danielxdrj`. Branch: `gh issue develop`.
- **D6. Sem transação banco+rede.** Checkpoint `*.md.forge-remote.json` + `--retomar <tarefa>`. Reconciliar com `gh issue view` antes de criar de novo. O Forge não apaga issue.

## Consequências

Testes usam Cursor e gh falsos. Nenhuma issue da empresa é criada por CI ou por agentes. Quem opera instala e autentica Cursor CLI e `gh` na própria máquina.
