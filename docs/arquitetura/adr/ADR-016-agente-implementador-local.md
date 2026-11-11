# ADR-016: agente implementador local (exceção limitada à FRG-43)

- **Status:** Aceito (11/11/2026), por decisão do responsável.
- **Data:** 2026-11-11.
- **Relaciona:** ADR-003 (adaptador), ADR-011 (orquestrador e privilegiados), ADR-013 / FRG-6 (sandbox em container), ADR-014 (papéis), ADR-015 (Cursor CLI).

## Contexto

A FRG-43 bloqueia agentes reais no orquestrador. O comando `resolver` precisa de um motor que **escreva código** a partir de uma issue. Isto não libera o registro de agentes privilegiados nem a autoaprovação.

## Decisão

- **D1. Exceção limitada.** Só o fluxo `resolver` (CLI local) pode chamar um motor implementador. `AgentRegistry`, `AgentRuntime` e `Orchestrator` continuam recusando privilegiados. Aprovação registrada **não** executa agente.
- **D2. Escrita só no clone temporário.** Cada execução clona o repositório-alvo num diretório `forge-resolver-*` apagado no fim (salvo `--manter-clone` / `--retomar`). `--trust` vale **somente** nesse clone. Sem `--force` / `--yolo` / `-f` / `--approve-mcps`. MCP e WebFetch negados no `cli.json`. O motor não recebe `GH_TOKEN`, `GITHUB_TOKEN`, `GH_*` (exceto o que o `gh` do Forge usa noutro processo), `FORGE_*` nem `DATABASE_URL`.
- **D3. Sem container.** Roda na máquina de quem opera (Windows incluído). Isolamento parcial; risco residual aceito (prompt injection via issue/repo, tools da CLI, custo do modelo).
- **D4. Quem opera.** Sessão humana autenticada (ADR-014) com papel **`editor`**. Owner **não** implica editor. Validações locais baratas (ref `owner/repo#n`, modelo) **antes** de login/rede/LLM.
- **D5. Forge publica.** O motor pode editar arquivos e rodar testes **dentro do clone**. Não faz `git push` nem usa `gh`. Depois da validação do diff e da confirmação humana `s`/`sim`, o Forge faz push e abre **PR em rascunho** com `Closes #n`. Nunca merge.
- **D6. Mesma porta.** `ProviderAdapter.complete`. Hoje: Cursor CLI em `--mode agent` no clone. Trocar para Claude Code = outro adaptador.

## Consequências

Testes usam motor e `gh` falsos. Nenhuma issue/PR de repositório real é criada por CI. Quem opera instala Cursor CLI e `gh` na própria máquina.
