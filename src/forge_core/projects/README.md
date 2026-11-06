# Projetos e repositórios (FRG-5, ADR-012)

Cadastro de vários projetos e repositórios numa instalação. Sem chamadas ao GitHub e sem token.

## Arquivos e responsabilidades
```
model.py    ProjectInfo, RepositoryInfo, RepositoryTarget (provider, owner, repo_name, base_branch, settings)
rules.py    validação pura: owner, repo, branch, provider, settings (chaves, 8 KB, filtro de segredo)
service.py  ProjectService: cadastrar, listar, editar, desativar/reativar, resolve_target; audita tudo
```
Tabelas: `projects` (estendida) e `repositories` (migração `0008`). Depende só da stdlib e do `SqlRepository`.

## Configuração
Nenhuma variável nova. Usa `FORGE_DATABASE_URL` (e `FORGE_DATABASE_MIGRATION_URL`), como o resto do Core.

## Cadastrar um projeto e um repositório
```python
repo = open_repository(settings.database_url)
svc = ProjectService(repo)
p = svc.create_project("Sistema X", "pessoa:ana", description="...")
r = svc.add_repository(p.id, "API", "minha-org", "sistema-x-api", "pessoa:ana", default_branch="main",
                       settings={"branch_prefix": "forge/", "issue_labels": ["forge"]})
svc.update_repository(r.id, "pessoa:ana", expected_version=r.version, default_branch="develop")
svc.deactivate_repository(r.id, "pessoa:ana")   # nunca apaga
target = svc.resolve_target(r.id)               # para a FRG-21; recusa inativo
```
`settings` aceita só `branch_prefix`, `issue_labels` e `base_branch_override`, até 8 KB, sem cara de segredo. Ao editar, `settings` substitui o objeto inteiro.

## Testar
`pytest tests/core/test_projects.py` (SQLite) e, com `FORGE_DATABASE_URL` apontando para um Postgres que possa criar banco/papel, o mesmo arquivo roda também no Postgres (inclui GRANT sem DELETE).

## Troubleshooting
- `repositório já cadastrado`: a identidade (provider, owner, repo) é única, sem diferenciar maiúsculas.
- `version esperada X, atual Y`: releia e repita a edição.
- `projeto inativo`: reative o projeto, depois o repositório.
- `permission denied` no Postgres: reexecute `postgres_roles.sql` (GRANT de `projects` e `repositories`).
- `settings com cara de segredo`: tire tokens e senhas; use o cofre.

## Limitações e próximos passos
Editor sem autenticação (aceito pelo gestor de projetos); existência no GitHub não verificada (FRG-21); tarefa sem `repository_id`. Próximos: veja a seção de sugestões do ADR-012.
