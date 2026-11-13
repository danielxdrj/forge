# CLAUDE.md

Antes de propor código, leia [`AGENTS.md`](AGENTS.md) (regras de segurança, escopo e
quando parar). Este arquivo só resume onde as coisas ficam e como rodar os testes.

## Não faça

- Não varra o repositório inteiro. Use Grep/Glob focados nos módulos abaixo.
- Nunca escreva em FTP, banco de dados ou Portainer conectados (`connections/`):
  o contrato é somente leitura (`connections/readonly.py`).
- Nunca vaze segredo, token ou conteúdo do vault Obsidian em prompt, log ou commit.
  Passe texto livre por `redaction.py` antes de sair do processo.
- Nunca use `--dangerously-skip-permissions` no Claude Code CLI.

## Mapa dos módulos

- API FastAPI: `src/forge_core/web/` (`app.py` registra rotas; um módulo por área:
  `connections.py`, `context_graph.py`, `graphs.py`, `issues.py`, `notes.py`,
  `tasks.py`, `agents.py`, `investigations.py`, `security.py`).
- Storage SQL: `src/forge_core/storage/` (`sql.py`, `migrate.py`); migrations numeradas
  em `storage/migrations/{postgres,sqlite}/NNNN_*.sql` (nunca edite uma já aplicada).
- Motor LLM: `draft/claude_cli.py`, `draft/cursor_cli.py`, `draft/engine.py`,
  `draft/service.py`, `resolver/service.py`, `resolver/context_pack.py`,
  `resolver/prompt.py`, `investigations/service.py`.
- Contexto do grafo (injetado em todo prompt do motor): `graphs/prompt_context.py`
  (`graph_prompt_section`). Use-o em vez de reler o grafo na mão.
- Grafos Graphify: `graphs/context.py`, `graphs/store.py`, `graphs/indexer.py`.
- Conexões (somente leitura real): `connections/{service,probes,vault,readonly}.py`.
- Issues: `issues/{store,importer,related}.py`, `draft/github_gh.py`.
- Agentes (orquestração/governança, aba "Agentes"): `agents.py` (web) sobre as
  tabelas `agents`/`agent_executions`/`agent_approvals`; não confundir com o pacote
  `src/forge_core/agents/` (orchestrator interno, ADR-011), que é outro conceito.

## Testes e lint

```
python -m pytest -q tests/core
python -m ruff check .
```

`backend/tests` cobre o backend legado (`backend/app/investigations.py`); mantenha-o
funcionando se mexer em algo compartilhado.
