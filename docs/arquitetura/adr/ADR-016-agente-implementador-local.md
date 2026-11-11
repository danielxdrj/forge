# ADR-016: agente implementador local (exceção limitada à FRG-43)

- **Status:** Aceito (11/11/2026), por decisão do responsável. Atualizado na revisão do PR do `resolver` (controles de git/gh).
- **Data:** 2026-11-11.
- **Relaciona:** ADR-003 (adaptador), ADR-011 (orquestrador e privilegiados), ADR-013 / FRG-6 (sandbox em container), ADR-014 (papéis), ADR-015 (Cursor CLI).

## Contexto

A FRG-43 bloqueia agentes reais no orquestrador. O comando `resolver` precisa de um motor que **escreva código** a partir de uma issue. Isto não libera o registro de agentes privilegiados nem a autoaprovação.

## Decisão

- **D1. Exceção limitada.** Só o fluxo `resolver` (CLI local) pode chamar um motor implementador. `AgentRegistry`, `AgentRuntime` e `Orchestrator` continuam recusando privilegiados. Aprovação registrada **não** executa agente.
- **D2. Escrita só no clone temporário.** Cada execução clona o repositório-alvo num diretório `forge-resolver-*` apagado no fim (salvo `--manter-clone` / `--retomar`). `--trust` vale **somente** nesse clone. Sem `--force` / `--yolo` / `-f` / `--approve-mcps`. MCP e WebFetch negados no `cli.json`. O motor não recebe `GH_TOKEN`, `GITHUB_TOKEN`, `GH_*` de credencial, `FORGE_*` nem `DATABASE_URL`.
- **D3. Sem container.** Roda na máquina de quem opera (Windows incluído). Isolamento parcial.
- **D4. Quem opera.** Sessão humana autenticada (ADR-014) com papel **`editor`**. Owner **não** implica editor. Validações locais baratas (ref `owner/repo#n`, modelo) **antes** de login/rede/LLM. Confirmação **sempre** interativa (`s`/`N`); não há `--yes`.
- **D5. Forge publica.** O motor pode editar arquivos e rodar testes **dentro do clone**. Não faz `git push` nem usa `gh`. O remote `origin` é **removido** antes do motor (URL no checkpoint). Depois de `s`/`sim`, o Forge reconta o hash do working tree, commita, reconfere a meta de `.git`, recoloca o `origin` e faz `git push origin HEAD:refs/heads/<branch>`. PR em **rascunho** com `Closes #n`. Nunca merge.
- **D6. Mesma porta.** `ProviderAdapter.complete`. Hoje: Cursor CLI em `--mode agent` no clone. Trocar para Claude Code = outro adaptador.
- **D7. Git/gh isolados no motor.** Env do motor: `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL` e `GH_CONFIG_DIR` em arquivos/dirs vazios no temp, `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `GIT_ASKPASS`/`SSH_ASKPASS` vazios, sem `SSH_AUTH_SOCK`. HOME/APPDATA podem permanecer para a Cursor CLI autenticar no Windows; git/gh do filho não devem achar credencial do operador.
- **D8. Meta de `.git` e hooks.** Snapshot de `.git/config`, `.git/hooks` (lista+hash), `.git/info` e ficheiros de config **antes** do motor; qualquer mudança → `git_meta_tampered` (fail-closed). Comandos git do Forge usam `-c core.hooksPath=<dir vazio>` `-c core.fsmonitor=false`; commit/push com `--no-verify`. No push, só esses `-c` + `--no-verify` (credencial do usuário necessária). Diff que adiciona/altera `.gitattributes` ou `.gitmodules` é recusado. `.cursor/cli.json` do Forge entra em `.git/info/exclude` e não vai ao commit.
- **D9. Hash atado.** O hash da prévia é o do working tree (incluindo ficheiros novos). Depois do `s` e no `--retomar` em fase `validated`, o hash é recalculado; divergência → `diff_changed`, sem push. Commit só depois do `s`.

## Risco residual (aceito)

`IMPLEMENTER_DENY` **não** cobre `Shell(*)`: o motor precisa editar e testar. O processo corre com o utilizador do SO. Isolamento de git/gh reduz, não elimina, a hipótese de o motor tentar push (sem `origin`, sem credencial git/gh no env). Prompt injection via issue/repo, isolamento parcial no Windows e custo do modelo continuam aceites.

## Consequências

Testes usam motor e `gh` falsos. Nenhuma issue/PR de repositório real é criada por CI. Quem opera instala Cursor CLI e `gh` na própria máquina.
