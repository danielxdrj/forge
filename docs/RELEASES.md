# Releases e Conventional Commits

As releases do Forge são **manuais**. Quem opera escolhe a versão, atualiza o `CHANGELOG.md`, sobe `project.version` em `pyproject.toml`, cria a tag `vX.Y.Z` e a GitHub Release. Não há workflow de release automática.

O `CHANGELOG.md` existente é histórico: acrescente uma seção nova no topo; não apague nem reescreva entradas já publicadas.

## Visão geral

| Peça | Arquivo | Papel |
| --- | --- | --- |
| Versão do pacote | `pyproject.toml` (`[project].version`) | Versão vigente do `forge-core`. |
| Histórico | `CHANGELOG.md` | Notas já publicadas. |
| Check do título do PR | `.github/workflows/pr-title.yml` | Falha se o título do PR não seguir Conventional Commits. |

## Regra vigente

PRs de feature e fix **não alteram** `pyproject.toml` nem o `CHANGELOG.md`. Quem sobe a versão e acrescenta a seção no CHANGELOG é o PR da própria release, depois de revisão.

## Fluxo

1. Um PR é mergeado na `main` com **squash merge**. O título do PR vira a mensagem do commit.
2. Quando houver commits que geram release (tabela abaixo), quem opera abre um PR `chore: release X.Y.Z` com `pyproject.toml` e uma seção nova no `CHANGELOG.md`.
3. Depois do merge na `main`, cria a tag anotada e a GitHub Release (procedimento abaixo).

A release não sai direto a cada push: a versão e as notas passam por um PR.

## Tipos de commit e efeito na versão

O formato é `<tipo>(<escopo opcional>)<!>: <descrição>`. Exemplos: `feat: listar investigações`, `fix(api): rejeitar log vazio`, `feat!: remover rota antiga`.

| Tipo | Efeito na versão | Aparece no CHANGELOG |
| --- | --- | --- |
| `feat` | minor (`0.20.0` → `0.21.0`) | Features |
| `fix` | patch | Bug Fixes |
| `perf` | patch | Performance Improvements |
| `revert` | patch | Reverts |
| `!` depois do tipo/escopo, ou `BREAKING CHANGE:` no rodapé | **major** | Seção do tipo, com aviso de breaking change |
| `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `style` | **nenhum** | não aparece |

Decisões documentadas:

- **Tipos sem release.** `docs`, `refactor`, `test`, `build`, `ci`, `chore` e `style` não mudam o comportamento para quem usa o Forge. Eles não geram release sozinhos e não entram nas notas. Ficam no histórico git e seguem junto com a próxima release de `feat`, `fix` ou `perf`.
- **Versões 0.x.** Breaking change gera **major** também antes da 1.0 (`0.20.0` → `1.0.0`).
- **Squash merge e `BREAKING CHANGE`.** Com squash merge, o corpo do commit nem sempre vem da descrição do PR. A forma confiável de marcar breaking change é o `!` no título do PR (`feat!: ...`).
- **Tag.** Formato `vX.Y.Z`.

## Check do título do PR

O workflow `PR title` roda em PRs (abertura, edição de título, novo commit, reabertura) e valida o título com uma expressão regular, sem ação de terceiros. Tipos aceitos: `feat`, `fix`, `perf`, `revert`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `style`. Escopo e `!` são opcionais. A descrição é obrigatória e depois dos dois-pontos vem um espaço.

Se a lista de tipos mudar, atualize `.github/workflows/pr-title.yml` e a tabela deste documento.

Opcional: em branch protection, marcar o check `PR title / validate` como obrigatório.

## Procedimento

Requer permissão de escrita no repositório.

1. Veja o que mudou desde a última release:

   ```bash
   git fetch --tags origin
   git log "$(git describe --tags --abbrev=0 origin/main)"..origin/main --format='%h %s'
   ```

2. Escolha a versão pela tabela de tipos acima: `feat` → minor, `fix`/`perf`/`revert` → patch, `!` ou `BREAKING CHANGE` → major. Sem nenhum desses, não há release.
3. Num branch `chore/release-X.Y.Z`, atualize:
   - `CHANGELOG.md`: nova seção `## [X.Y.Z](...) (AAAA-MM-DD)` com os commits agrupados por tipo (`### Features`, `### Bug Fixes`, ...); não altere seções já publicadas;
   - `pyproject.toml`: `[project].version = "X.Y.Z"`;
   - abra o PR, com título `chore: release X.Y.Z`, e faça o merge.
4. Crie a tag no commit da `main` resultante e publique a release:

   ```bash
   git switch main && git pull origin main
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <arquivo-com-as-notas>
   ```

   Pela interface: **Releases → Draft a new release**, escolher a tag, colar as notas e publicar.

O botão "Generate release notes" do GitHub agrupa por PR e label, não por tipo de commit. Para notas por tipo, copie as seções do `CHANGELOG.md`.

Quando existir um deploy, ele deve rodar em `push` na `main` ou ser chamado por `workflow_dispatch`/`workflow_call`, e não por `on: push: tags` ou `on: release` (eventos de tag/release criados com `GITHUB_TOKEN` não disparam outros workflows).
