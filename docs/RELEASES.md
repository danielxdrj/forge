# Releases e Conventional Commits

Este documento descreve a automação de releases do Forge: como ela decide a versão, o que ela cria, como desativá-la e como fazer a mesma coisa à mão. A automação é opcional. Nenhum processo da empresa depende dela, porque o procedimento manual abaixo produz o mesmo resultado.

## Visão geral

| Peça | Arquivo | Papel |
| --- | --- | --- |
| Workflow de release | `.github/workflows/release.yml` | A cada push na `main`, roda o [release-please](https://github.com/googleapis/release-please-action) com o `GITHUB_TOKEN`. |
| Configuração | `release-please-config.json` | Tipos de commit, seções do CHANGELOG, formato da tag (`vX.Y.Z`). |
| Versão atual | `.release-please-manifest.json` | Última versão **publicada** (`0.15.0`, tag `v0.15.0` em `6f853f6`). Atualizado pelo próprio PR de release. |
| Check do título do PR | `.github/workflows/pr-title.yml` | Falha se o título do PR não seguir Conventional Commits. |
| Saídas | `CHANGELOG.md`, `version.txt`, tag `vX.Y.Z`, GitHub Release | Criados quando o PR de release é mergeado. |

> **Regra vigente (substitui qualquer procedimento anterior):** PRs de feature e fix **não alteram** `.release-please-manifest.json`, `pyproject.toml` nem `version` em lugar nenhum. Quem sobe a versão é o release-please, no PR `chore(main): release X.Y.Z`. O `pyproject.toml` entra como `extra-files` em `release-please-config.json` para ser atualizado junto. O manifesto só é corrigido à mão em caso excepcional de estado inconsistente, como a correção de 0.16.0 para 0.15.0 feita no PR de autenticação humana, porque o manifesto precisa apontar para a última versão publicada. Não usar `release-as` permanente.

Só o `GITHUB_TOKEN` é usado. Não há segredo pessoal, token de acesso pessoal nem GitHub App.

## Fluxo

1. Um PR é mergeado na `main` com **squash merge**. O título do PR vira a mensagem do commit.
2. O workflow `Release` roda. Se houver commits que geram release (tabela abaixo), ele abre ou atualiza um PR chamado `chore(main): release X.Y.Z`. Esse PR contém o `CHANGELOG.md`, o `version.txt` e o `.release-please-manifest.json` atualizados.
3. Uma pessoa revisa e **mergeia** o PR de release (merge normal, sem alterar o título). Esse é o ponto de aprovação humana da release.
4. Ao mergear, o workflow cria a tag `vX.Y.Z` e a GitHub Release, com as notas agrupadas por tipo.

Escolha deliberada: a release não sai direto a cada push. O PR de release permite conferir versão e notas antes de publicar. A alternativa de publicar direto no push foi descartada (veja a comparação no fim).

## Tipos de commit e efeito na versão

O formato é `<tipo>(<escopo opcional>)<!>: <descrição>`. Exemplos: `feat: listar investigações`, `fix(api): rejeitar log vazio`, `feat!: remover rota antiga`.

| Tipo | Efeito na versão | Aparece no CHANGELOG |
| --- | --- | --- |
| `feat` | minor (`0.9.1` → `0.10.0`) | Features |
| `fix` | patch | Bug Fixes |
| `perf` | patch | Performance Improvements |
| `revert` | patch | Reverts |
| `!` depois do tipo/escopo, ou `BREAKING CHANGE:` no rodapé | **major** | Seção do tipo, com aviso de breaking change |
| `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `style` | **nenhum** | não aparece |

Decisões documentadas:

- **Tipos sem release.** `docs`, `refactor`, `test`, `build`, `ci`, `chore` e `style` não mudam o comportamento para quem usa o Forge. Eles não geram release sozinhos e não entram nas notas. Ficam no histórico git e seguem junto com a próxima release de `feat`, `fix` ou `perf`. A alternativa (tratá-los como patch) foi descartada para não publicar uma release a cada ajuste de documentação. Para mudar isso, altere `"hidden": true` para `false` no tipo em `release-please-config.json`; o tipo passa a gerar patch.
- **Versões 0.x.** O Forge está em `0.9.1`. Está configurado `bump-minor-pre-major: false`, então um breaking change gera **major** também antes da 1.0 (`0.9.1` → `1.0.0`), como pedido. Se a equipe preferir que breaking change em 0.x gere minor, mude para `true` em `release-please-config.json`.
- **Squash merge e `BREAKING CHANGE`.** Com squash merge, o corpo do commit nem sempre vem da descrição do PR. A forma confiável de marcar breaking change é o `!` no título do PR (`feat!: ...`).
- **Tag.** Formato `vX.Y.Z`, o mesmo das tags `v0.1.0` a `v0.9.1` já existentes.

## Check do título do PR

O workflow `PR title` roda em PRs (abertura, edição de título, novo commit, reabertura) e valida o título com uma expressão regular, sem ação de terceiros. Tipos aceitos: `feat`, `fix`, `perf`, `revert`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `style`. Escopo e `!` são opcionais. A descrição é obrigatória e depois dos dois-pontos vem um espaço.

Se a lista de tipos mudar, atualize **os dois** arquivos: `.github/workflows/pr-title.yml` e `release-please-config.json`.

## Configuração única no GitHub (requer administrador do repositório)

Estas configurações não ficam no código e não foram alteradas pela automação:

1. **Settings → Actions → General → Workflow permissions:** marcar **Allow GitHub Actions to create and approve pull requests**. Sem isso, o release-please não consegue abrir o PR de release.
2. **Settings → General → Pull Requests → Allow squash merging → Default commit message:** escolher **Pull request title** (ou "Pull request title and description"). A configuração atual do repositório é `squash_merge_commit_title: COMMIT_OR_PR_TITLE` (verificada pela API do GitHub em 2026-11-06): o GitHub usa o título do PR só quando o PR tem mais de um commit. Num PR de um commit só, o título que vai para a `main` é o do commit, e o título validado pelo check pode não ser o que define a versão.
3. Opcional: em branch protection, marcar o check `PR title / validate` como obrigatório.

## Limitações conhecidas

- **Workflows não são disparados por eventos do `GITHUB_TOKEN`.** O PR de release criado pelo release-please não executa checks (por exemplo `PR title`). Se a `main` exigir checks obrigatórios, esse PR ficará bloqueado e será preciso um administrador mergeá-lo. A tag e a Release criadas também não disparam outros workflows. Quando existir um deploy, ele deve rodar em `push` na `main` ou ser chamado por `workflow_dispatch`/`workflow_call`, e não por `on: push: tags` ou `on: release`. Usar um token pessoal ou um GitHub App contornaria isso, mas está fora do requisito de usar só o `GITHUB_TOKEN`.
- **Sem testes no pipeline.** Este repositório ainda não tem workflow de CI que rode testes. A release não verifica que os testes passam.
- **Histórico anterior.** As releases `v0.1.0` a `v0.9.1` foram criadas à mão (a `v0.9.1` marca o commit do relatório da FRG-32, `b0d14f4`) e não existe `CHANGELOG.md` anterior. O primeiro CHANGELOG automático lista só o que vier depois da tag `v0.9.1`.
- **Numeração herdada de código legado.** **[Informado pelo responsável]** O código que existia até a tag `v0.9.0` é de outro projeto, não do Forge atual. O manifesto parte de `0.9.1` porque é a última tag do repositório. Se o Forge atual deve recomeçar a numeração (por exemplo em `0.1.0`) ou usar um repositório novo, ajuste `.release-please-manifest.json` e a tag base antes de a automação ser ativada, ou use a chave `RELEASE_AUTOMATION_ENABLED=false` até a decisão. A decisão está em aberto (relatório da FRG-32, PR #10).
- **Arquivo `version.txt`.** O Forge ainda não tem um manifesto de versão único (`pyproject.toml`, `package.json` com versão). O tipo de release `simple` mantém a versão num `version.txt` na raiz. Quando houver um lugar oficial para a versão, troque o `release-type` e documente aqui.

## Como desativar

Da mais leve para a mais definitiva:

1. **Sem alterar código:** em **Settings → Secrets and variables → Actions → Variables**, crie a variável de repositório `RELEASE_AUTOMATION_ENABLED` com o valor `false`. O job `release-please` passa a ser ignorado. Para reativar, apague a variável ou mude o valor.
2. **Pela interface:** em **Actions**, escolha o workflow `Release` (ou `PR title`) e use **Disable workflow**.
3. **Definitivo:** remova `.github/workflows/release.yml`, `.github/workflows/pr-title.yml`, `release-please-config.json` e `.release-please-manifest.json` num PR. Se existir um PR de release aberto (`chore(main): release ...`), feche-o e apague a branch `release-please--branches--main`.
4. Se o check `PR title / validate` foi marcado como obrigatório em branch protection, desmarque antes de desativar o workflow. Senão, os PRs ficam esperando um check que nunca roda.

Desativar a automação não apaga tags, releases nem o `CHANGELOG.md` já criados.

## Procedimento manual equivalente

Use quando a automação estiver desativada ou indisponível. Requer permissão de escrita no repositório.

1. Veja o que mudou desde a última release:

   ```bash
   git fetch --tags origin
   git log "$(git describe --tags --abbrev=0 origin/main)"..origin/main --format='%h %s'
   ```

2. Escolha a versão pela tabela de tipos acima: `feat` → minor, `fix`/`perf`/`revert` → patch, `!` ou `BREAKING CHANGE` → major. Sem nenhum desses, não há release.
3. Num branch `chore/release-X.Y.Z`, atualize:
   - `CHANGELOG.md`: nova seção `## X.Y.Z (AAAA-MM-DD)` com os commits agrupados por tipo (`### Features`, `### Bug Fixes`, ...);
   - `version.txt` e `.release-please-manifest.json` com `X.Y.Z` (se a automação for reativada depois, esse arquivo precisa refletir a última versão lançada);
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

## Comparação das ferramentas

Critérios: ferramenta padrão e mantida, uso só do `GITHUB_TOKEN`, repositório com Python e JavaScript sem manifesto de versão único.

| Critério | release-please (escolhida) | semantic-release |
| --- | --- | --- |
| Manutenção | Mantida pela Google; `release-please-action` v5.0.0 é a última versão em 2026-11-06. | Mantida pela comunidade; amplamente usada. |
| Modelo | Abre PR de release; a release sai quando o PR é mergeado. Aprovação humana embutida. | Publica direto a cada push. |
| Configuração | Dois arquivos JSON e um workflow. Não exige Node no projeto para funcionar. | Exige Node, arquivo de configuração e plugins (`changelog`, `git`, `github`) com versões a manter. |
| Repositório com `main` protegida | Funciona com a branch protegida (a mudança vai por PR). | O plugin `git` precisa dar push direto do CHANGELOG na `main`, o que normalmente exige token com bypass de proteção. |
| Só `GITHUB_TOKEN` | Sim. | Sim, mas o push na `main` protegida costuma exigir token mais poderoso. |
| Linguagens | Agnóstico (`release-type: simple`). | Agnóstico, mas a cultura e os plugins são centrados em npm. |

A versão e a situação de manutenção do release-please foram verificadas em 2026-11-06. As informações sobre o semantic-release vêm de conhecimento geral e não foram reverificadas nesta data.

`release-drafter` (rascunhos por label de PR, não por commit) e `git-cliff` (só gera CHANGELOG, sem tag nem release) também foram considerados e não atendem sozinhos aos requisitos.
