import os
from pathlib import Path

os.environ.setdefault("GOOGLE_SHEET_ID", "metrics-test")
os.environ.setdefault("CACHE_DB_PATH", str(Path("metrics-test.db")))

from fastapi.testclient import TestClient

from sheetbridge.config import settings
from sheetbridge.main import app


def test_metrics_endpoint(tmp_path: Path):
    previous_path = settings.CACHE_DB_PATH
    settings.CACHE_DB_PATH = str(tmp_path / "t.db")
    try:
        with TestClient(app) as client:
            response = client.get("/metrics")
    finally:
        settings.CACHE_DB_PATH = previous_path
    assert response.status_code == 200
    assert b"sheetbridge_requests_total" in response.content
