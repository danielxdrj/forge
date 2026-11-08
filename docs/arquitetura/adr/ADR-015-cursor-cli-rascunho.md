# ADR-015: rascunho de issue com Cursor CLI e gh local

- **Status:** Aceito (08/11/2026). O responsável aceitou o risco residual de ferramentas da Cursor CLI não serem 100% desligáveis.
- **Data:** 2026-11-08.
- **Relaciona:** ADR-003 (adaptador de provedor), ADR-007 (GitHub), ADR-010 (tarefa), ADR-012 (prefixo de branch), ADR-014 (papel editor).

## Contexto

O Forge precisa redigir um rascunho de issue a partir de contexto livre e, depois de confirmação humana, criar a issue no GitHub com o `gh` já autenticado na máquina de quem opera. A Cursor CLI foi escolhida como primeiro LLM. A documentação oficial **não garante** invocação sem ferramentas; `--print` declara acesso a write e shell.

## Decisão

- **D1. Isolamento aceito, não absoluto.** Cada chamada cria um diretório temporário **vazio** novo (`mkdtemp`), usa `--workspace` nesse diretório, `--mode ask`, `--print` / `--output-format text`, e um `.cursor/cli.json` do projeto com `permissions.deny` nos tokens **documentados** em https://cursor.com/docs/cli/reference/permissions (`Shell(*)`, `Shell(*:*)`, `Read(*)`, `Read(**/*)`, `Read(/**)`, equivalentes de `Write`, `WebFetch(*)`, `Mcp(*:*)`). Não se usa `Shell()` / `Read()` vazios (não há garantia de glob universal). Não se usa `--force`, `--trust`, `--yolo`, `--approve-mcps`. O diretório é removido no `finally`.
- **D2. Risco residual.** Deny + pasta vazia **não** são sandbox forte. A CLI pode ainda tentar tools. Isto foi aceito explicitamente. Não há garantia total.
- **D3. Interface única `ProviderAdapter.complete`.** Só contexto do usuário + instrução do template entram no prompt. Sem credencial Forge/GitHub/banco. Claude Code fica para troca futura de adaptador, não nesta entrega.
- **D4. Env allowlist.** O subprocesso Cursor recebe PATH, HOME/USERPROFILE/APPDATA (login nativo da CLI) e, se existirem, `CURSOR_API_KEY` / `CURSOR_AUTH_TOKEN` de sessão. Não recebe `GH_TOKEN`, `GITHUB_TOKEN`, `FORGE_*`, `DATABASE_URL`. O subprocesso `gh` (só depois da confirmação, no Forge) recebe allowlist própria, também sem esses tokens; usa o keyring nativo.
- **D5. gh só no Forge.** Preview + `s`/`N` (default N). `--yes` pula só o prompt. Qualquer `[PENDENTE]` em campo obrigatório bloqueia. Falha de project: mostrar `gh auth refresh -s project`, não executar. `gh issue create` devolve URL (sem `--json`). Sprint/opções: `gh api graphql` documentado (field-list não traz iterations). Assignee `danielxdrj`. Branch: `gh issue develop`.
- **D6. Sem transação banco+rede.** Checkpoint `*.md.forge-remote.json` + `--retomar <tarefa>`. Reconciliar com `gh issue view` antes de criar de novo. O Forge não apaga issue.

## Consequências

Testes usam Cursor e gh falsos. Nenhuma issue da empresa é criada por CI ou por agentes. Quem opera instala e autentica Cursor CLI e `gh` na própria máquina.
