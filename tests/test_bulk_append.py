import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sheetbridge.config import reload_settings, settings
from sheetbridge.main import app
import sheetbridge.store as store


def _client(tmp_path: Path, overrides: dict[str, str] | None = None) -> TestClient:
    db_path = tmp_path / "bulk.db"
    env = {
        "CACHE_DB_PATH": str(db_path),
        "GOOGLE_SHEET_ID": "test-sheet",
        "API_KEYS": "k1",
        "ALLOW_WRITE_BACK": "0",
        "KEY_COLUMN": "id",
        "UPSERT_STRICT": "1",
    }
    if overrides:
        env.update({key: str(value) for key, value in overrides.items()})
    for key, value in env.items():
        os.environ[key] = value
    reload_settings()
    if store.engine is not None:
        store.engine.dispose()
    if db_path.exists():
        db_path.unlink()
    store.refresh_engine()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup():
    tracked_env = {
        key: os.environ.get(key)
        for key in [
            "CACHE_DB_PATH",
            "GOOGLE_SHEET_ID",
            "API_KEYS",
            "ALLOW_WRITE_BACK",
            "KEY_COLUMN",
            "UPSERT_STRICT",
            "BULK_MAX_ITEMS",
        ]
    }
    settings_snapshot = {
        "CACHE_DB_PATH": settings.CACHE_DB_PATH,
        "GOOGLE_SHEET_ID": settings.GOOGLE_SHEET_ID,
        "API_KEYS": settings.API_KEYS,
        "ALLOW_WRITE_BACK": settings.ALLOW_WRITE_BACK,
        "KEY_COLUMN": settings.KEY_COLUMN,
        "UPSERT_STRICT": settings.UPSERT_STRICT,
        "BULK_MAX_ITEMS": settings.BULK_MAX_ITEMS,
    }
    yield
    db_path = Path(settings.CACHE_DB_PATH)
    if db_path.exists():
        db_path.unlink()
    if store.engine is not None:
        store.engine.dispose()
        store.engine = None
    for key, value in tracked_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    for key, value in settings_snapshot.items():
        setattr(settings, key, value)


def test_bulk_mixed(tmp_path: Path):
    with _client(tmp_path) as client:
        body = [{"id": "1", "name": "A"}, {"name": "no_id"}]
        response = client.post(
            "/bulk/append", headers={"X-API-Key": "k1"}, json=body
        )
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] == [0]
    assert len(data["rejected"]) == 1
    assert data["count"] == 1


def test_bulk_missing_key_not_strict(tmp_path: Path):
    overrides = {"UPSERT_STRICT": "0"}
    with _client(tmp_path, overrides=overrides) as client:
        body = [{"id": "1", "name": "A"}, {"name": "no_id"}]
        response = client.post(
            "/bulk/append", headers={"X-API-Key": "k1"}, json=body
        )
        rows = store.list_rows()
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] == [0, 1]
    assert data["rejected"] == []
    assert data["count"] == 2
    assert len(rows) == 2


def test_bulk_idempotency(tmp_path: Path):
    with _client(tmp_path) as client:
        payload = [{"id": "1"}]
        headers = {"X-API-Key": "k1", "Idempotency-Key": "batch-1"}
        first = client.post("/bulk/append", headers=headers, json=payload)
        second = client.post("/bulk/append", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "1"
    assert first.json() == second.json()


def test_bulk_limit(tmp_path: Path):
    overrides = {"BULK_MAX_ITEMS": "10"}
    with _client(tmp_path, overrides=overrides) as client:
        too_many = [{"id": str(i)} for i in range(1000)]
        response = client.post(
            "/bulk/append", headers={"X-API-Key": "k1"}, json=too_many
        )
    assert response.status_code == 413
