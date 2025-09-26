import os
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path("test_rows_filters.db")
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet")
os.environ.setdefault("CACHE_DB_PATH", str(TEST_DB_PATH))

from sheetbridge.main import app
from sheetbridge.store import insert_rows, init_db


@pytest.fixture(autouse=True)
def reset_db():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    init_db()
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def _client() -> TestClient:
    return TestClient(app)


def test_projection_and_total():
    insert_rows(
        [
            {"id": "1", "name": "Alice", "city": "Auburn"},
            {"id": "2", "name": "Bob", "city": "Boston"},
        ]
    )
    with _client() as client:
        response = client.get(
            "/rows",
            params={"columns": "id,name", "limit": "1", "offset": "0"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["rows"]) == 1
    assert set(body["rows"][0].keys()) == {"id", "name"}


def test_q_filter():
    insert_rows([
        {"id": "1", "name": "Mike"},
        {"id": "2", "name": "Other"},
    ])
    with _client() as client:
        response = client.get("/rows", params={"q": "mik"})
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert any(str(value).lower().find("mik") != -1 for row in rows for value in row.values())


def test_since_filter():
    insert_rows([
        {"id": "1"},
    ])
    time.sleep(1)
    insert_rows([
        {"id": "2"},
    ])
    since = str(int(time.time()) - 1)
    with _client() as client:
        response = client.get("/rows", params={"since": since})
    assert response.status_code == 200
    ids = {row.get("id") for row in response.json()["rows"]}
    assert "2" in ids
