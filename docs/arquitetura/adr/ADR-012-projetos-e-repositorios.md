# ADR-012: Projetos e repositórios gerenciáveis

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** a FRG-21 (GitHub) for implementada, existir autenticação de quem edita, ou entrar um provider além do GitHub

## Contexto
A FRG-15 criou `projects` e `stages` mínimas (id, título, data). A FRG-5 precisa gerenciar vários projetos e repositórios numa única instalação de uso interno (sem multi-inquilino). A FRG-21 depende deste modelo para criar issue e branch (etapa 3 do fluxo operacional do Forge).

## Decisões
- **Extensão sem reescrita.** A migração `0008` acrescenta a `projects` as colunas `description`, `active`, `version` e `updated_at` (linhas existentes: ativo, versão 1, `updated_at = created_at`) e cria `repositories`. `stages`, `tasks` e `TaskService` não mudam; `tasks.Project` segue como visão enxuta, e `projects.ProjectInfo` é o modelo completo. A tarefa não ganha `repository_id` agora (sugestão de tarefa futura).
- **Repositório.** Um projeto tem N repositórios. Campos: nome, `provider` (fixo `github`, coluna pronta para outros), `owner`, `repo_name`, `default_branch`, `active`, `settings`, `version`. Identidade única por `(provider, lower(owner), lower(repo_name))`: o mesmo repositório não entra em dois projetos (o GitHub ignora maiúsculas).
- **Ativo/inativo, sem DELETE.** Desativar é `active = 0`. Desativar o projeto desativa seus repositórios na mesma transação. Reativar o projeto não reativa repositórios; reativar repositório de projeto inativo é recusado; projeto inativo não aceita repositório novo. O GRANT do escritor não tem DELETE (e `projects` ganhou UPDATE).
- **Concorrência.** Edição exige `expected_version` (conflito: `ProjectConflictError`); `FOR UPDATE` no Postgres e `BEGIN IMMEDIATE` no SQLite.
- **Configuração por repositório: no banco** (`repositories.settings`, JSON), e não em arquivo versionado. Prós: editável pelo serviço, auditada, atômica com o cadastro, sem deploy e sem dados da empresa no código do Core. Contra: não passa por revisão de PR (mitigado por auditoria e validação). Descartado: arquivo versionado (mistura dado da empresa com o Core, risco de segredo no Git) e híbrido (duas fontes). Regras: só as chaves `branch_prefix` (ex.: `forge/`), `issue_labels` (até 20) e `base_branch_override`; até 8 KB; valores validados; valores com cara de segredo (`redact()` ou formato de token do GitHub/AWS) são recusados. Segredo e token nunca ficam aqui; no futuro, só referência ao cofre.
- **Validação (regras puras):** owner (1-39, letras/números/hífen, sem hífen no início/fim/duplo), repo (1-100, `[A-Za-z0-9._-]`, não termina em `.git`), branch (regras de ref do Git), provider.
- **Auditoria.** Toda operação grava na mesma transação (`project.create|update|deactivate|reactivate`, `repository.create|update|deactivate|reactivate`); recusas também. A auditoria guarda ids e nomes de campos, nunca valores livres. Mensagens de validação são fixas (códigos como `invalid_provider` e `unknown_settings_key`, no máximo com nome de campo e contagem) e nunca interpolam entrada do chamador; ids do chamador só entram no alvo da auditoria se tiverem formato de UUID (senão `<tipo>:unknown`); o texto do erro passa por `redact()`. O mesmo vale para o `TaskService`.

## Como a FRG-21 consome isto
`ProjectService.resolve_target(repository_id)` devolve `(provider, owner, repo_name, base_branch, settings)` e recusa repositório ou projeto inativo/inexistente (`ProjectRuleError`). `base_branch` é `settings.base_branch_override` se existir, senão `default_branch`. Na criação da issue e da branch, a FRG-21 usa `settings.branch_prefix` para nomear a branch e `settings.issue_labels` para as labels. Ela só lê: o Core não faz nenhuma chamada ao GitHub, não guarda token, e se a FRG-21 precisar de nova convenção, a chave entra na lista permitida por ADR/PR. O token virá do cofre de segredos, fora deste modelo.

## Limitações (aceitas pelo gestor de projetos)
- O editor é o ator informado, sem autenticação nem permissões por pessoa ou cliente.
- A existência do repositório no GitHub não é verificada (FRG-21).
- Os bancos já provisionados precisam reexecutar `postgres_roles.sql` para o GRANT de UPDATE em `projects` e SELECT/INSERT/UPDATE em `repositories`.
- A visão `tasks.Project` não mostra `active`.

## Sugestões de tarefas futuras
1. Ligar tarefa a repositório (`repository_id`). 2. Referência a segredos por repositório, no cofre. 3. Autenticação e permissões de quem edita. 4. Ciclo de vida de projeto além de ativo/inativo (arquivado).

## Consequências
O Core ganha um cadastro pronto para a FRG-21 sem tecnologia nova nem dado da empresa. O custo é mais uma tabela e uma lista de chaves de `settings` a manter.
