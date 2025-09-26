import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sheetbridge.config import settings
from sheetbridge.main import app
from sheetbridge.scheduler import state as sync_state


def _reset_scheduler_state() -> None:
    sync_state.running = False
    sync_state.last_started = None
    sync_state.last_finished = None
    sync_state.last_error = None
    sync_state.total_runs = 0
    sync_state.total_errors = 0


@pytest.fixture(autouse=True)
def restore_settings():
    original = {
        "SYNC_ENABLED": getattr(settings, "SYNC_ENABLED", False),
        "SYNC_INTERVAL_SECONDS": getattr(settings, "SYNC_INTERVAL_SECONDS", 300),
        "SYNC_JITTER_SECONDS": getattr(settings, "SYNC_JITTER_SECONDS", 15),
        "SYNC_BACKOFF_MAX_SECONDS": getattr(settings, "SYNC_BACKOFF_MAX_SECONDS", 600),
        "CACHE_DB_PATH": getattr(settings, "CACHE_DB_PATH", "sheetbridge.db"),
    }
    _reset_scheduler_state()
    yield
    for key, value in original.items():
        setattr(settings, key, value)
    _reset_scheduler_state()


def test_scheduler_disabled_by_default(tmp_path: Path):
    db_path = tmp_path / "disabled.db"
    settings.CACHE_DB_PATH = str(db_path)
    settings.SYNC_ENABLED = False

    with TestClient(app) as client:
        response = client.get("/sync/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["running"] is False
    assert body["total_runs"] == 0
    assert body["total_errors"] == 0

    if db_path.exists():
        db_path.unlink()


def test_scheduler_recovers_without_credentials(tmp_path: Path):
    db_path = tmp_path / "no-creds.db"
    settings.CACHE_DB_PATH = str(db_path)
    settings.SYNC_ENABLED = True
    settings.SYNC_INTERVAL_SECONDS = 1
    settings.SYNC_JITTER_SECONDS = 0
    settings.SYNC_BACKOFF_MAX_SECONDS = 2

    with TestClient(app) as client:
        # Allow enough time for the first scheduled run to execute and record an error.
        time.sleep(2.5)
        response = client.get("/sync/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["interval"] == 1
    assert body["jitter"] == 0
    assert body["backoff_max"] == 2
    assert body["total_errors"] >= 1
    assert body["last_error"] in (None, "Google credentials not configured")

    if db_path.exists():
        db_path.unlink()
