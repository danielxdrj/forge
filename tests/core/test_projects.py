import pytest

from forge_core.errors import ProjectConflictError, ProjectRuleError
from forge_core.projects import ProjectService
from forge_core.projects import rules

ACTOR = "pessoa:ana"


@pytest.fixture
def env(make_repo):
    repo = make_repo()
    return repo, ProjectService(repo)


def audit(repo):
    return [(a.action, a.target, a.result) for a in repo.list_audit()]


def two_projects(svc):
    p1, p2 = svc.create_project("Alfa", ACTOR), svc.create_project("Beta", ACTOR, "segundo")
    r1 = svc.add_repository(p1.id, "api", "empresa-x", "alfa-api", ACTOR, default_branch="main")
    r2 = svc.add_repository(p2.id, "web", "empresa-x", "beta-web", ACTOR, default_branch="develop")
    return p1, p2, r1, r2


def test_two_projects_with_distinct_repositories_list_edit_deactivate(env):
    repo, svc = env
    p1, p2, r1, r2 = two_projects(svc)
    assert [p.title for p in svc.list_projects()] == ["Alfa", "Beta"]
    assert [r.repo_name for r in svc.list_repositories()] == ["alfa-api", "beta-web"]
    assert [r.id for r in svc.list_repositories(project_id=p2.id)] == [r2.id]
    assert svc.get_repository(r1.id) == r1 and svc.get_project(p1.id) == p1

    edited = svc.update_repository(r1.id, ACTOR, 1, default_branch="trunk", name="API alfa")
    assert (edited.default_branch, edited.name, edited.version) == ("trunk", "API alfa", 2)
    assert svc.get_repository(r1.id) == edited
    pe = svc.update_project(p1.id, ACTOR, 1, title="Alfa 2")
    assert pe.title == "Alfa 2" and pe.version == 2

    svc.deactivate_repository(r2.id, ACTOR)
    assert [r.id for r in svc.list_repositories(active_only=True)] == [r1.id]
    assert len(svc.list_repositories()) == 2  # nada é apagado
    svc.deactivate_project(p2.id, ACTOR)
    assert [p.id for p in svc.list_projects(active_only=True)] == [p1.id]


def test_identity_is_unique_per_provider_owner_repo_case_insensitive(env):
    repo, svc = env
    p1, p2, r1, _ = two_projects(svc)
    with pytest.raises(ProjectRuleError, match="já cadastrado"):
        svc.add_repository(p2.id, "dup", "Empresa-X", "ALFA-API", ACTOR)  # outro projeto, mesmo repositório
    with pytest.raises(ProjectRuleError, match="já cadastrado"):
        svc.add_repository(p1.id, "dup", "empresa-x", "alfa-api", ACTOR)
    other = svc.add_repository(p1.id, "ok", "empresa-x", "alfa-api-2", ACTOR)
    with pytest.raises(ProjectRuleError, match="já cadastrado"):
        svc.update_repository(other.id, ACTOR, 1, repo_name="alfa-api")
    assert len(svc.list_repositories()) == 3
    assert audit(repo)[-1][2].startswith("error: repositório já cadastrado")


def test_deactivation_cascades_and_reactivation_of_inactive_project_repo_is_refused(env):
    repo, svc = env
    p1, _, r1, _ = two_projects(svc)
    r1b = svc.add_repository(p1.id, "b", "empresa-x", "alfa-b", ACTOR)
    svc.deactivate_repository(r1b.id, ACTOR)
    res = svc.deactivate_project(p1.id, ACTOR)
    assert not res.active and not svc.get_repository(r1.id).active
    with pytest.raises(ProjectRuleError, match="projeto inativo"):
        svc.reactivate_repository(r1.id, ACTOR)
    with pytest.raises(ProjectRuleError, match="projeto inativo"):
        svc.add_repository(p1.id, "c", "empresa-x", "alfa-c", ACTOR)
    assert not svc.get_repository(r1.id).active
    svc.reactivate_project(p1.id, ACTOR)
    assert not svc.get_repository(r1.id).active  # reativar o projeto não reativa repositórios
    assert svc.reactivate_repository(r1.id, ACTOR).active


@pytest.mark.parametrize("owner", ["", "-a", "a-", "a--b", "a b", "a/b", "x" * 40, "açai"])
def test_invalid_owner(env, owner):
    _, svc = env
    p = svc.create_project("P", ACTOR)
    with pytest.raises(ProjectRuleError, match="owner"):
        svc.add_repository(p.id, "n", owner, "r", ACTOR)


@pytest.mark.parametrize("name", ["", ".", "..", "a b", "a/b", "x.git", "x" * 101])
def test_invalid_repo_name(env, name):
    _, svc = env
    p = svc.create_project("P", ACTOR)
    with pytest.raises(ProjectRuleError, match="repo_name"):
        svc.add_repository(p.id, "n", "org", name, ACTOR)


@pytest.mark.parametrize("branch", ["", " ", "a b", "a..b", "a~1", "a:b", "a?", "a*", "a[", "/a", "a/", "a.", "-a", "a//b",
                                    "a@{b", "@", ".hidden", "x/.y", "x.lock", "a\\b"])
def test_invalid_branch(env, branch):
    _, svc = env
    p = svc.create_project("P", ACTOR)
    with pytest.raises(ProjectRuleError, match="default_branch"):
        svc.add_repository(p.id, "n", "org", "r", ACTOR, default_branch=branch)


@pytest.mark.parametrize("branch", ["main", "release/1.0", "feature/x-y_z", "v1.2.3"])
def test_valid_branch(branch):
    assert rules.validate_branch(branch) == branch


def test_provider_and_required_fields(env):
    _, svc = env
    p = svc.create_project("P", ACTOR)
    with pytest.raises(ProjectRuleError, match="provider"):
        svc.add_repository(p.id, "n", "org", "r", ACTOR, provider="gitlab")
    with pytest.raises(ProjectRuleError, match="título"):
        svc.create_project("  ", ACTOR)
    with pytest.raises(ProjectRuleError, match="nome"):
        svc.add_repository(p.id, " ", "org", "r", ACTOR)
    with pytest.raises(ProjectRuleError, match="inexistente"):
        svc.add_repository("nao-existe", "n", "org", "r", ACTOR)


def test_settings_valid_and_replaced_whole(env):
    _, svc = env
    p = svc.create_project("P", ACTOR)
    r = svc.add_repository(p.id, "n", "org", "r", ACTOR, settings={
        "branch_prefix": "forge/", "issue_labels": ["forge", "bug"], "base_branch_override": "release/1.0"})
    assert svc.get_repository(r.id).settings["issue_labels"] == ["forge", "bug"]
    r2 = svc.update_repository(r.id, ACTOR, 1, settings={"branch_prefix": "bot/"})
    assert svc.get_repository(r.id).settings == {"branch_prefix": "bot/"} and r2.version == 2


@pytest.mark.parametrize("settings, msg", [
    ({"token": "abc"}, "desconhecida"),
    ({"branch_prefix": "forge/", "ghp_token": "x"}, "desconhecida"),
    ({"branch_prefix": "x" * 9000}, "8192"),
    ({"issue_labels": ["ghp_" + "A" * 36]}, "segredo"),
    ({"issue_labels": ["github_pat_" + "B" * 30]}, "segredo"),
    ({"issue_labels": ["password: abc123"]}, "segredo"),
    ({"branch_prefix": "../x/"}, "branch_prefix"),
    ({"branch_prefix": "a b/"}, "branch_prefix"),
    ({"issue_labels": "bug"}, "lista"),
    ({"issue_labels": ["a"] * 21}, "lista"),
    ({"issue_labels": ["a,b"]}, "label"),
    ({"issue_labels": ["Bug", "bug"]}, "repetidas"),
    ({"base_branch_override": "a..b"}, "base_branch_override"),
    ("texto", "objeto"),
])
def test_settings_refused(env, settings, msg):
    repo, svc = env
    p = svc.create_project("P", ACTOR)
    with pytest.raises(ProjectRuleError, match=msg):
        svc.add_repository(p.id, "n", "org", "r", ACTOR, settings=settings)
    assert svc.list_repositories() == []
    r = svc.add_repository(p.id, "n", "org", "r", ACTOR)
    with pytest.raises(ProjectRuleError, match=msg):
        svc.update_repository(r.id, ACTOR, 1, settings=settings)
    assert svc.get_repository(r.id).settings == {} and svc.get_repository(r.id).version == 1


def test_version_conflict(env):
    repo, svc = env
    p1, _, r1, _ = two_projects(svc)
    svc.update_repository(r1.id, ACTOR, 1, name="novo")
    with pytest.raises(ProjectConflictError):
        svc.update_repository(r1.id, ACTOR, 1, name="outro")
    with pytest.raises(ProjectConflictError):
        svc.deactivate_repository(r1.id, ACTOR, expected_version=1)
    svc.update_project(p1.id, ACTOR, 1, title="x")
    with pytest.raises(ProjectConflictError):
        svc.update_project(p1.id, ACTOR, 1, title="y")
    with pytest.raises(ProjectConflictError):
        svc.deactivate_project(p1.id, ACTOR, expected_version=1)
    assert svc.get_repository(r1.id).name == "novo" and svc.get_project(p1.id).title == "x"
    assert audit(repo)[-1][2].startswith("error: version desatualizada")


def test_resolve_target(env):
    _, svc = env
    p = svc.create_project("P", ACTOR)
    plain = svc.add_repository(p.id, "n", "org", "plain", ACTOR, default_branch="develop")
    over = svc.add_repository(p.id, "n", "org", "over", ACTOR, settings={
        "branch_prefix": "forge/", "issue_labels": ["forge"], "base_branch_override": "release/2"})
    provider, owner, repo_name, base, settings = svc.resolve_target(plain.id)
    assert (provider, owner, repo_name, base, settings) == ("github", "org", "plain", "develop", {})
    t = svc.resolve_target(over.id)
    assert t.base_branch == "release/2" and t.settings["branch_prefix"] == "forge/"
    t.settings["branch_prefix"] = "alterado"  # cópia: não afeta o banco
    assert svc.resolve_target(over.id).settings["branch_prefix"] == "forge/"
    with pytest.raises(ProjectRuleError, match="inexistente"):
        svc.resolve_target("nao-existe")
    svc.deactivate_repository(plain.id, ACTOR)
    with pytest.raises(ProjectRuleError, match="repositório inativo"):
        svc.resolve_target(plain.id)
    svc.deactivate_project(p.id, ACTOR)
    with pytest.raises(ProjectRuleError, match="projeto inativo"):
        svc.resolve_target(over.id)


def test_audit_log_records_operations_without_free_text(env):
    repo, svc = env
    p = svc.create_project("Alfa", ACTOR, "descricao-sigilosa")
    r = svc.add_repository(p.id, "n", "org", "r", ACTOR, settings={"issue_labels": ["rotulo-x"]})
    svc.update_repository(r.id, ACTOR, 1, default_branch="dev", settings={"branch_prefix": "f/"})
    svc.update_project(p.id, ACTOR, 1, title="Alfa 2")
    svc.deactivate_project(p.id, "pessoa:bia")
    with pytest.raises(ProjectRuleError):
        svc.reactivate_repository(r.id, ACTOR)
    rows = audit(repo)
    assert ("project.create", f"project:{p.id}", "ok") in rows
    assert ("repository.create", f"repository:{r.id}", "ok") in rows
    assert ("repository.update", f"repository:{r.id}", "ok: fields=default_branch,settings") in rows
    assert ("project.update", f"project:{p.id}", "ok: fields=title") in rows
    assert ("project.deactivate", f"project:{p.id}", "ok: repositories=1") in rows
    assert ("repository.deactivate", f"repository:{r.id}", "ok: cascade") in rows
    assert rows[-1][0] == "repository.reactivate" and rows[-1][2].startswith("error:")
    assert {a.actor for a in repo.list_audit() if a.action == "project.deactivate"} == {"pessoa:bia"}
    flat = repr(rows)
    assert "descricao-sigilosa" not in flat and "rotulo-x" not in flat


def test_existing_task_projects_get_defaults_and_stay_compatible(env):
    from forge_core.tasks import TaskService

    _, svc = env
    old = TaskService(svc._repo).create_project("Legado", ACTOR)
    info = svc.get_project(old.id)
    assert info.active and info.version == 1 and info.description == "" and info.updated_at == old.created_at


@pytest.mark.parametrize("sql", ["UPDATE projects SET title = 'x'", "DELETE FROM projects", "TRUNCATE projects",
                                 "DELETE FROM repositories", "TRUNCATE repositories"])
def test_postgres_writer_has_no_delete_or_truncate(pg_env, sql):
    import psycopg

    writer, _, _ = pg_env
    svc = ProjectService(writer)
    p = svc.create_project("P", ACTOR)
    svc.add_repository(p.id, "n", "org", "r", ACTOR)
    if sql.startswith("UPDATE"):  # UPDATE é permitido (desativar/editar); só DELETE/TRUNCATE não
        svc.update_project(p.id, ACTOR, 1, title="ok")
        return
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer._run([(sql, ())])


SENTINEL = "ghp_" + "Z" * 36 + "SENTINELA-UNICA"


def _assert_no_sentinel(repo, caplog):
    assert SENTINEL not in repr([(a.actor, a.action, a.target, a.result) for a in repo.list_audit()])
    assert SENTINEL not in repr(repo.fetch("SELECT * FROM task_changes"))
    assert SENTINEL not in caplog.text


def _refused(fn, *args, **kw):
    with pytest.raises(Exception) as ei:
        fn(*args, **kw)
    assert SENTINEL not in str(ei.value) and ei.type.__name__ in ("ProjectRuleError", "ProjectConflictError", "TaskRuleError", "TaskConflictError", "KeyError")


def test_sentinel_never_reaches_audit_or_logs_from_projects(env, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    repo, svc = env
    p = svc.create_project("P", ACTOR)
    r = svc.add_repository(p.id, "n", "org", "r", ACTOR)
    s = SENTINEL
    _refused(svc.add_repository, p.id, "n", "org", "r2", ACTOR, provider=s)
    _refused(svc.add_repository, p.id, "n", "org", "r2", ACTOR, settings={s: "x"})
    _refused(svc.update_repository, r.id, ACTOR, 1, settings={s: "x"})
    _refused(svc.add_repository, p.id, "n", s, "r2", ACTOR)
    _refused(svc.update_repository, r.id, ACTOR, 1, owner=s)
    _refused(svc.add_repository, p.id, "n", "org", s + "/x", ACTOR)
    _refused(svc.update_repository, r.id, ACTOR, 1, repo_name=s + "/x")
    _refused(svc.add_repository, p.id, "n", "org", "r2", ACTOR, default_branch=s + " x")
    _refused(svc.update_repository, r.id, ACTOR, 1, default_branch=s + "~")
    _refused(svc.add_repository, p.id, "n", "org", "r2", ACTOR, settings={"branch_prefix": s + " "})
    _refused(svc.add_repository, p.id, "n", "org", "r2", ACTOR, settings={"issue_labels": [s]})
    _refused(svc.add_repository, p.id, "n", "org", "r2", ACTOR, settings={"base_branch_override": s + ".."})
    _refused(svc.add_repository, p.id, "x" * 101 + s, "org", "r2", ACTOR)
    _refused(svc.create_project, s * 10, ACTOR)
    _refused(svc.update_project, s, ACTOR, 1, title="x")
    _refused(svc.update_repository, s, ACTOR, 1, name="x")
    _refused(svc.add_repository, s, "n", "org", "r2", ACTOR)
    _refused(svc.deactivate_project, s, ACTOR)
    _refused(svc.reactivate_repository, s, ACTOR)
    _refused(svc.resolve_target, s)
    _refused(svc.update_repository, r.id, ACTOR, s)
    _assert_no_sentinel(repo, caplog)
    rows = [a.result for a in repo.list_audit() if a.result.startswith("error")]
    assert any("invalid_provider" in x for x in rows) and any("unknown_settings_key" in x for x in rows)


def test_sentinel_never_reaches_audit_from_task_service(env, caplog):
    import logging

    from forge_core.tasks import TaskService

    caplog.set_level(logging.DEBUG)
    repo, _ = env
    ts = TaskService(repo)
    t = ts.create_task("t", ACTOR)
    s = SENTINEL
    _refused(ts.create_task, "t", ACTOR, priority=s)
    _refused(ts.create_task, "t", ACTOR, assignee_kind=s, assignee_id="x")
    _refused(ts.create_task, "t", ACTOR, stage_id=s)
    _refused(ts.create_task, "t", ACTOR, parent_id=s)
    _refused(ts.create_task, "t", ACTOR, due_date=s)
    _refused(ts.update_task, t.id, ACTOR, 1, **{s: "x"})
    _refused(ts.update_task, s, ACTOR, 1, title="x")
    _refused(ts.change_status, t.id, s, ACTOR)
    _refused(ts.change_status, s, "done", ACTOR)
    _refused(ts.create_stage, s, "e", ACTOR)
    _refused(ts.add_dependency, t.id, s, ACTOR)
    _refused(ts.add_dependency, s, t.id, ACTOR)
    _assert_no_sentinel(repo, caplog)
