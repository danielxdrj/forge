-- Issues concluídas importadas (somente leitura no GitHub). Upsert por repo+number.
CREATE TABLE completed_issues (
    repo text NOT NULL,
    number integer NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    labels_json text NOT NULL,
    prs_json text NOT NULL,
    closed_at text,
    url text NOT NULL,
    imported_at text NOT NULL,
    PRIMARY KEY (repo, number)
);
CREATE INDEX completed_issues_closed ON completed_issues (repo, closed_at);
