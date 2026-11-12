-- Issues concluídas importadas (somente leitura no GitHub). Upsert por repo+number.
CREATE TABLE completed_issues (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    labels_json TEXT NOT NULL,
    prs_json TEXT NOT NULL,
    closed_at TEXT,
    url TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY (repo, number)
);
CREATE INDEX completed_issues_closed ON completed_issues (repo, closed_at);
