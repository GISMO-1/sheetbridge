from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from sheetbridge import ratelimit
from sheetbridge.config import settings
from sheetbridge.main import app


@contextmanager
def _client(tmp_path: Path, rate_limit: bool = False):
    db_path = tmp_path / "metrics.db"
    if db_path.exists():
        db_path.unlink()
    previous = (
        settings.CACHE_DB_PATH,
        settings.GOOGLE_SHEET_ID,
        settings.RATE_LIMIT_ENABLED,
        settings.RATE_LIMIT_RPS,
        settings.RATE_LIMIT_BURST,
    )
    settings.CACHE_DB_PATH = str(db_path)
    settings.GOOGLE_SHEET_ID = "test"
    settings.RATE_LIMIT_ENABLED = rate_limit
    settings.RATE_LIMIT_RPS = 5.0
    settings.RATE_LIMIT_BURST = 2
    ratelimit._buckets.clear()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        settings.CACHE_DB_PATH, settings.GOOGLE_SHEET_ID, settings.RATE_LIMIT_ENABLED, settings.RATE_LIMIT_RPS, settings.RATE_LIMIT_BURST = previous
        if db_path.exists():
            db_path.unlink()


def test_metrics_endpoint(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert b"sb_requests_total" in response.content


def test_rate_limit_blocks(tmp_path: Path) -> None:
    with _client(tmp_path, rate_limit=True) as client:
        first = client.get("/health")
        second = client.get("/health")
        third = client.get("/health")
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code in (200, 429)
