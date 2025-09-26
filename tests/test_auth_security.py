import os
from pathlib import Path

from fastapi.testclient import TestClient

from sheetbridge.config import settings
from sheetbridge.main import app


def _client(tmp: Path, api_keys: str = "k1") -> TestClient:
    db_path = tmp / "t.db"
    os.environ["CACHE_DB_PATH"] = str(db_path)
    os.environ["GOOGLE_SHEET_ID"] = "test"
    os.environ["API_KEYS"] = api_keys
    settings.CACHE_DB_PATH = str(db_path)
    settings.GOOGLE_SHEET_ID = "test"
    settings.API_KEYS = api_keys
    return TestClient(app)


def _cleanup_db(path: Path) -> None:
    if path.exists():
        path.unlink()


def test_admin_rejects_without_key(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    with _client(tmp_path) as client:
        response = client.post("/admin/idempotency/purge")
    _cleanup_db(db_path)
    settings.API_KEYS = ""
    os.environ["API_KEYS"] = ""
    assert response.status_code == 401


def test_admin_accepts_with_key(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    with _client(tmp_path) as client:
        response = client.post(
            "/admin/idempotency/purge",
            headers={"X-API-Key": "k1"},
        )
    _cleanup_db(db_path)
    settings.API_KEYS = ""
    os.environ["API_KEYS"] = ""
    assert response.status_code == 200
    assert "purged" in response.json()
