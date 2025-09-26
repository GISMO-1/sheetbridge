import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet")
os.environ.setdefault("CACHE_DB_PATH", "test-append.db")

from sheetbridge.config import settings
from sheetbridge.main import app


@pytest.fixture(autouse=True)
def _reset_db(tmp_path: Path):
    yield
    db_path = Path(getattr(settings, "CACHE_DB_PATH", "sheetbridge.db"))
    if db_path.exists():
        db_path.unlink()


def _set_setting(name: str, value):
    if name == "ALLOW_WRITE_BACK":
        parsed = str(value).lower() in {"1", "true", "yes", "on"}
        setattr(settings, name, parsed)
    else:
        setattr(settings, name, value)


def _client(env: dict[str, object]):
    for key, value in env.items():
        os.environ[key] = str(value)
        if hasattr(settings, key):
            _set_setting(key, value)
    return TestClient(app)


def test_append_requires_token(tmp_path: Path):
    with _client(
        {
            "ALLOW_WRITE_BACK": "1",
            "CACHE_DB_PATH": str(tmp_path / "t.db"),
            "GOOGLE_SHEET_ID": "test",
        }
    ) as client:
        response = client.post("/append", json={"x": 1})
    assert response.status_code == 401


def test_append_forbidden_when_disabled(tmp_path: Path):
    with _client(
        {
            "ALLOW_WRITE_BACK": "0",
            "CACHE_DB_PATH": str(tmp_path / "t.db"),
            "GOOGLE_SHEET_ID": "test",
        }
    ) as client:
        response = client.post(
            "/append",
            headers={"Authorization": "Bearer dev_token"},
            json={"x": 1},
        )
    assert response.status_code == 403


def test_append_accepts_without_creds_returns_202_like(tmp_path: Path):
    with _client(
        {
            "ALLOW_WRITE_BACK": "1",
            "CACHE_DB_PATH": str(tmp_path / "t.db"),
            "GOOGLE_SHEET_ID": "test",
        }
    ) as client:
        response = client.post(
            "/append",
            headers={"Authorization": "Bearer dev_token"},
            json={"x": 1},
        )
    assert response.status_code == 200
    assert response.json() == {"inserted": 1, "wrote": False}
