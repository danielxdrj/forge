"""Exclusão de issue (GitHub + registros locais), inclusive issue não criada pelo Forge.

Escrita externa explícita: exige confirmação exata (`owner/repo#numero`) e papel `owner`.
Tenta apagar via GraphQL `deleteIssue`; sem permissão de admin, recusa com código claro e
permite fechar como `not planned` (`fallback=close`). Depois limpa registros locais para a
issue não reaparecer: `completed_issues`, rascunhos/vínculos de tarefa e notas/investigações
ligadas (desvinculadas por padrão; apagadas de vez só com `purge_notes=true`).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..auth.store import AuthStore, Principal
from ..draft.github_gh import GhCli
from ..errors import DraftError, ForgeError
from ..storage.sql import SqlRepository


class IssueDeleteError(ForgeError):
    """Validação ou recusa da exclusão. Código fixo; nunca inclui token nem stdout do gh."""

    def __init__(self, code: str, hint: str = ""):
        super().__init__(code if not hint else f"{code}: {hint}")
        self.code = code
        self.hint = hint


@dataclass(frozen=True)
class IssueDeleteResult:
    repo: str
    number: int
    mode: str  # "deleted" | "closed"


def issue_key(repo: str, number: int) -> str:
    return f"{repo}#{number}"


class IssueDeleteService:
    def __init__(self, repo: SqlRepository, store: AuthStore, gh: GhCli | None):
        self._repo = repo
        self._store = store
        self._gh = gh

    def delete(
        self, principal: Principal, owner: str, repo_name: str, number: int,
        confirm: str, *, fallback: str | None = None, purge_notes: bool = False,
    ) -> IssueDeleteResult:
        self._store.require(principal, "owner")
        owner = (owner or "").strip()
        repo_name = (repo_name or "").strip()
        if not owner or not repo_name or number < 1:
            raise IssueDeleteError("invalid_issue")
        full_repo = f"{owner}/{repo_name}"
        expected = issue_key(full_repo, number)
        if (confirm or "").strip() != expected:
            raise IssueDeleteError("confirm_mismatch")
        if self._gh is None:
            raise IssueDeleteError("gh_missing")
        mode = self._delete_or_close(full_repo, number, fallback=fallback)
        self._purge_local(full_repo, number, purge_notes=purge_notes)
        self._repo.record_audit(
            principal.identity_id, "issue.delete", f"issue:{expected}",
            f"ok: mode={mode} purge_notes={purge_notes}",
        )
        return IssueDeleteResult(full_repo, number, mode)

    def _delete_or_close(self, full_repo: str, number: int, *, fallback: str | None) -> str:
        try:
            self._gh.delete_issue(full_repo, number)
            return "deleted"
        except DraftError as exc:
            if exc.code != "issue_delete_forbidden":
                raise IssueDeleteError(exc.code) from exc
            if fallback != "close":
                raise IssueDeleteError(
                    "issue_delete_forbidden",
                    "sem permissão de admin para apagar; envie fallback=\"close\" para "
                    "fechar a issue como not planned",
                ) from exc
            try:
                self._gh.close_issue_not_planned(full_repo, number)
            except DraftError as close_exc:
                raise IssueDeleteError(close_exc.code) from close_exc
            return "closed"

    def _purge_local(self, full_repo: str, number: int, *, purge_notes: bool) -> None:
        key = issue_key(full_repo, number)
        with self._repo.transaction() as tx:
            rows = tx.execute(
                "SELECT task_id FROM task_links WHERE kind = 'issue' "
                "AND lower(repo) = lower(?) AND number = ?",
                (full_repo, number),
            ).fetchall()
            for (task_id,) in rows:
                tx.execute("DELETE FROM drafts WHERE task_id = ?", (task_id,))
                tx.execute("DELETE FROM task_links WHERE task_id = ?", (task_id,))
            tx.execute(
                "DELETE FROM completed_issues WHERE lower(repo) = lower(?) AND number = ?",
                (full_repo, number),
            )
            if purge_notes:
                tx.execute(
                    "DELETE FROM investigation_notes WHERE lower(issue_key) = lower(?)", (key,),
                )
            else:
                tx.execute(
                    "UPDATE investigation_notes SET issue_key = NULL WHERE lower(issue_key) = lower(?)",
                    (key,),
                )
            tx.audit(
                "sistema:issue_delete", "issue.purge_local", f"issue:{key}",
                f"ok: tasks={len(rows)} purge_notes={purge_notes}",
            )
        # issues/related.py e graphs/context.py leem completed_issues/investigation_notes direto
        # (sem cache própria fora da assinatura de ContextGraph, que já muda com a contagem acima):
        # a issue apagada some da próxima leitura, sem passo extra.
