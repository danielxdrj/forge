import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        with connect() as connection:
            connection.execute("TRUNCATE investigations RESTART IDENTITY")
        yield test_client


def test_create_and_read_investigation(client: TestClient) -> None:
    created = client.post("/investigations", json={"title": "Fechamento diario"})

    assert created.status_code == 201
    body = created.json()
    assert body["id"] == 1
    assert body["title"] == "Fechamento diario"
    assert body["created_at"]

    fetched = client.get(f"/investigations/{body['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Fechamento diario"
    assert fetched.json()["created_at"] == body["created_at"]


def test_record_survives_a_new_connection(client: TestClient) -> None:
    created = client.post("/investigations", json={"title": "Persiste"}).json()

    with connect() as connection:
        row = connection.execute(
            "SELECT title FROM investigations WHERE id = %s",
            (created["id"],),
        ).fetchone()

    assert row is not None
    assert row["title"] == "Persiste"

    fetched = client.get(f"/investigations/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Persiste"


@pytest.mark.parametrize("payload", [{}, {"title": ""}, {"title": "   "}])
def test_rejects_blank_title(client: TestClient, payload: dict[str, str]) -> None:
    response = client.post("/investigations", json=payload)

    assert response.status_code == 422
    with connect() as connection:
        count = connection.execute("SELECT count(*) AS total FROM investigations").fetchone()
    assert count is not None
    assert count["total"] == 0


def test_missing_investigation_returns_not_found(client: TestClient) -> None:
    response = client.get("/investigations/999")

    assert response.status_code == 404


def test_title_with_sql_text_is_stored_as_text(client: TestClient) -> None:
    title = "titulo'; DROP TABLE investigations; --"
    created = client.post("/investigations", json={"title": title})

    assert created.status_code == 201
    fetched = client.get(f"/investigations/{created.json()['id']}")
    assert fetched.json()["title"] == title
