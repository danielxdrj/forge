CREATE TABLE IF NOT EXISTS investigations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title varchar(200) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    investigation_id bigint NOT NULL REFERENCES investigations (id),
    origin text NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
