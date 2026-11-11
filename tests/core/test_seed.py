from forge_core.storage.seed import (
    ALLOWED_REPOS,
    DEFAULT_BRANCH,
    ORG,
    PROJECT_TITLE,
    list_active_allowed_repos,
    seed_allowed_repos,
)
from forge_core.projects.service import ProjectService
from auth_helpers import actor


def test_seed_is_idempotent_and_lists_active_allowed(make_repo):
    repo = make_repo()
    first = seed_allowed_repos(repo)
    second = seed_allowed_repos(repo)
    assert first == second
    names = {(r.owner, r.repo_name, r.provider, r.default_branch) for r in list_active_allowed_repos(repo)}
    expected = {(ORG, name, "github", DEFAULT_BRANCH) for name in ALLOWED_REPOS}
    assert expected <= names
    projects = [p for p in ProjectService(repo).list_projects() if p.title == PROJECT_TITLE]
    assert len(projects) == 1
    assert projects[0].id == first


def test_list_active_allowed_repos_skips_inactive_project(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    svc = ProjectService(repo)
    ana = actor(repo, "ana")
    forge = [p for p in svc.list_projects() if p.title == PROJECT_TITLE][0]
    svc.deactivate_project(forge.id, ana)
    assert list_active_allowed_repos(repo) == []


def test_list_active_allowed_repos_excludes_extra_repo(make_repo):
    repo = make_repo()
    seed_allowed_repos(repo)
    svc = ProjectService(repo)
    ana = actor(repo, "ana")
    forge = [p for p in svc.list_projects() if p.title == PROJECT_TITLE][0]
    extra = svc.add_repository(forge.id, "outro", ORG, "nao-na-lista", ana)
    names = {(r.owner, r.repo_name) for r in list_active_allowed_repos(repo)}
    assert (ORG, extra.repo_name) not in names
    assert (ORG, "site") in names
