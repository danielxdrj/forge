CREATE TABLE IF NOT EXISTS investigations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title varchar(200) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
