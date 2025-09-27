import os
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from sheetbridge.config import settings
from sheetbridge.main import app


@contextmanager
def _client(tmp: Path):
    env = {
        "CACHE_DB_PATH": str(tmp / "cache.db"),
        "GOOGLE_SHEET_ID": "test-sheet",
        "ALLOW_WRITE_BACK": "1",
        "KEY_COLUMN": "id",
        "UPSERT_STRICT": "1",
        "API_KEYS": "k1",
    }
    originals = {key: getattr(settings, key) for key in env if hasattr(settings, key)}
    for key, value in env.items():
        os.environ[key] = value
        lower = value.lower() if isinstance(value, str) else str(value).lower()
        if key == "ALLOW_WRITE_BACK":
            setattr(settings, key, lower in {"1", "true", "yes", "on"})
        elif key == "UPSERT_STRICT":
            setattr(settings, key, lower in {"1", "true", "yes", "on"})
        else:
            setattr(settings, key, value)
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        for key in env:
            os.environ.pop(key, None)
        for key, value in originals.items():
            setattr(settings, key, value)
        db_path = Path(env["CACHE_DB_PATH"])
        if db_path.exists():
            db_path.unlink()


def test_upsert_replaces(tmp_path: Path):
    with _client(tmp_path) as client:
        first = client.post("/append", headers={"X-API-Key": "k1"}, json={"id": "123", "val": 1})
        assert first.status_code == 200
        second = client.post("/append", headers={"X-API-Key": "k1"}, json={"id": "123", "val": 2})
        assert second.status_code == 200
        rows = client.get("/rows").json()["rows"]
        assert any(row.get("val") == 2 for row in rows)


def test_missing_key_rejected(tmp_path: Path):
    with _client(tmp_path) as client:
        response = client.post("/append", headers={"X-API-Key": "k1"}, json={"val": 1})
        assert response.status_code == 422


def test_dupes_endpoint(tmp_path: Path):
    with _client(tmp_path) as client:
        client.post("/append", headers={"X-API-Key": "k1"}, json={"id": "a"})
        client.post("/append", headers={"X-API-Key": "k1"}, json={"id": "b"})
        response = client.get("/admin/dupes", headers={"X-API-Key": "k1"})
        assert response.status_code == 200
        body = response.json()
        assert "duplicates" in body
