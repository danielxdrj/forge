"""Persistência de issues concluídas. Upsert por repo+number. Sem log do corpo."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..storage.sql import SqlRepository

UPSERT = (
    "INSERT INTO completed_issues "
    "(repo, number, title, body, labels_json, prs_json, closed_at, url, imported_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (repo, number) DO UPDATE SET "
    "title = excluded.title, body = excluded.body, labels_json = excluded.labels_json, "
    "prs_json = excluded.prs_json, closed_at = excluded.closed_at, url = excluded.url, "
    "imported_at = excluded.imported_at"
)


@dataclass(frozen=True)
class CompletedIssue:
    repo: str
    number: int
    title: str
    body: str
    labels: dict
    prs: list
    closed_at: str | None
    url: str
    imported_at: str

    @property
    def issue_key(self) -> str:
        return f"{self.repo}#{self.number}"

    def as_json(self, *, include_body: bool = False) -> dict:
        data = {
            "repo": self.repo,
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "closed_at": self.closed_at,
            "labels": self.labels,
            "prs": self.prs,
            "imported_at": self.imported_at,
            "issue_key": self.issue_key,
        }
        if include_body:
            data["body"] = self.body
        return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert(repo: SqlRepository, record: dict, *, imported_at: str | None = None) -> CompletedIssue:
    labels = record.get("labels") or {}
    if isinstance(labels, list):
        labels = {
            "tipo": str(record.get("tipo") or ""),
            "prioridade": str(record.get("prioridade") or ""),
            "sprint": str(record.get("sprint") or ""),
            "names": [str(x) for x in labels if str(x).strip()],
        }
    if not isinstance(labels, dict):
        labels = {"tipo": "", "prioridade": "", "sprint": "", "names": []}
    labels = {
        "tipo": str(labels.get("tipo") or record.get("tipo") or ""),
        "prioridade": str(labels.get("prioridade") or record.get("prioridade") or ""),
        "sprint": str(labels.get("sprint") or record.get("sprint") or ""),
        "names": [str(n) for n in (labels.get("names") or []) if str(n).strip()],
    }
    prs = record.get("prs") or []
    if not isinstance(prs, list):
        prs = []
    ts = imported_at or _now()
    row = (
        str(record["repo"]),
        int(record["number"]),
        str(record.get("title") or ""),
        str(record.get("body") or ""),
        json.dumps(labels, ensure_ascii=False),
        json.dumps(prs, ensure_ascii=False),
        record.get("closed_at") or None,
        str(record.get("url") or ""),
        ts,
    )
    with repo.transaction() as tx:
        tx.execute(UPSERT, row)
    return CompletedIssue(
        row[0], row[1], row[2], row[3], labels, prs, row[6], row[7], ts,
    )


def list_all(repo: SqlRepository) -> list[CompletedIssue]:
    rows = repo.fetch(
        "SELECT repo, number, title, body, labels_json, prs_json, closed_at, url, imported_at "
        "FROM completed_issues ORDER BY repo, number",
    )
    return [_from_row(r) for r in rows]


def get_one(repo: SqlRepository, full_repo: str, number: int) -> CompletedIssue | None:
    rows = repo.fetch(
        "SELECT repo, number, title, body, labels_json, prs_json, closed_at, url, imported_at "
        "FROM completed_issues WHERE lower(repo) = lower(?) AND number = ?",
        (full_repo, int(number)),
    )
    if not rows:
        return None
    return _from_row(rows[0])


def _from_row(row: tuple) -> CompletedIssue:
    labels = _loads(row[4], {})
    prs = _loads(row[5], [])
    if not isinstance(labels, dict):
        labels = {}
    if not isinstance(prs, list):
        prs = []
    return CompletedIssue(
        row[0], int(row[1]), row[2], row[3], labels, prs, row[6], row[7], row[8],
    )


def _loads(raw, default):
    if isinstance(raw, (dict, list)):
        return raw
    try:
        data = json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return default
    return data
