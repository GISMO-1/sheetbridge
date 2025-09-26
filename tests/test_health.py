import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path("test_sheetbridge.db")
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet")
os.environ.setdefault("CACHE_DB_PATH", str(TEST_DB_PATH))

from sheetbridge.main import app


@pytest.fixture(scope="module", autouse=True)
def cleanup_db():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def test_health_endpoint_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "time" in body
