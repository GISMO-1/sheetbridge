import os
from pathlib import Path

from fastapi.testclient import TestClient

from sheetbridge.config import settings
from sheetbridge.main import app
from sheetbridge.store import dlq_write


def _client(tmp: Path):
    os.environ["CACHE_DB_PATH"] = str(tmp / "t.db")
    os.environ["GOOGLE_SHEET_ID"] = "t"
    os.environ["API_KEYS"] = "k1"
    settings.CACHE_DB_PATH = str(tmp / "t.db")
    settings.GOOGLE_SHEET_ID = "t"
    settings.API_KEYS = "k1"
    return TestClient(app)


def test_dlq_admin_retry_no_creds(tmp_path: Path):
    keys = ["CACHE_DB_PATH", "GOOGLE_SHEET_ID", "API_KEYS"]
    original_env = {key: os.environ.get(key) for key in keys}
    original_settings = {
        "CACHE_DB_PATH": getattr(settings, "CACHE_DB_PATH", None),
        "GOOGLE_SHEET_ID": getattr(settings, "GOOGLE_SHEET_ID", None),
        "API_KEYS": getattr(settings, "API_KEYS", ""),
    }
    try:
        with _client(tmp_path) as client:
            dlq_write("write_failed", {"id": "1"})
            response = client.post("/admin/dlq/retry", headers={"X-API-Key": "k1"})
            assert response.status_code == 503
            assert "no creds" in response.text
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        settings.CACHE_DB_PATH = original_settings["CACHE_DB_PATH"]
        settings.GOOGLE_SHEET_ID = original_settings["GOOGLE_SHEET_ID"]
        settings.API_KEYS = original_settings["API_KEYS"]
