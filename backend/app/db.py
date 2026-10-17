import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Defina DATABASE_URL no ambiente.")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row)


def init_schema(connection: psycopg.Connection) -> None:
    connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def get_connection() -> Iterator[psycopg.Connection]:
    with connect() as connection:
        yield connection
