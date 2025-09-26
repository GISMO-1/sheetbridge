import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet")
os.environ.setdefault("CACHE_DB_PATH", "test-idempotency.db")

from sheetbridge.config import settings
from sheetbridge.main import app
import sheetbridge.store as store


def _set_setting(name: str, value):
    if name == "ALLOW_WRITE_BACK":
        parsed = str(value).lower() in {"1", "true", "yes", "on"}
        setattr(settings, name, parsed)
    elif hasattr(settings, name):
        setattr(settings, name, int(value) if str(value).isdigit() else value)


def _reset_engine(db_path: Path):
    if db_path.exists():
        db_path.unlink()
    if hasattr(store, "engine"):
        store.engine.dispose()
    store.engine = create_engine(f"sqlite:///{db_path}", echo=False)


def _client(env: dict[str, object], tmp_path: Path):
    for key, value in env.items():
        os.environ[key] = str(value)
        _set_setting(key, value)
    db_path = Path(env.get("CACHE_DB_PATH", settings.CACHE_DB_PATH))
    if not db_path.is_absolute():
        db_path = tmp_path / db_path
        os.environ["CACHE_DB_PATH"] = str(db_path)
        _set_setting("CACHE_DB_PATH", str(db_path))
    _reset_engine(db_path)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup(tmp_path: Path):
    yield
    db_path = Path(getattr(settings, "CACHE_DB_PATH", "sheetbridge.db"))
    if db_path.exists():
        db_path.unlink()
    if hasattr(store, "engine"):
        store.engine.dispose()


def test_append_without_idempotency_key_inserts_each_time(tmp_path: Path):
    with _client(
        {
            "ALLOW_WRITE_BACK": "1",
            "CACHE_DB_PATH": "idem-a.db",
            "GOOGLE_SHEET_ID": "test",
        },
        tmp_path,
    ) as client:
        first = client.post(
            "/append",
            headers={"Authorization": "Bearer dev_token"},
            json={"x": 1},
        )
        second = client.post(
            "/append",
            headers={"Authorization": "Bearer dev_token"},
            json={"x": 2},
        )
        rows = client.get("/rows")

    assert first.status_code == 200
    assert first.json() == {
        "inserted": 1,
        "wrote": False,
        "idempotency_key": None,
    }
    assert second.status_code == 200
    assert second.json() == {
        "inserted": 1,
        "wrote": False,
        "idempotency_key": None,
    }
    assert rows.json()["rows"] == [{"x": 1}, {"x": 2}]


def test_append_with_idempotency_key_replays_response(tmp_path: Path):
    with _client(
        {
            "ALLOW_WRITE_BACK": "1",
            "CACHE_DB_PATH": "idem-b.db",
            "GOOGLE_SHEET_ID": "test",
        },
        tmp_path,
    ) as client:
        first = client.post(
            "/append",
            headers={
                "Authorization": "Bearer dev_token",
                "Idempotency-Key": "K",
            },
            json={"x": 10},
        )
        replay = client.post(
            "/append",
            headers={
                "Authorization": "Bearer dev_token",
                "Idempotency-Key": "K",
            },
            json={"x": 11},
        )
        rows = client.get("/rows")

    assert first.status_code == 200
    assert first.json() == {
        "inserted": 1,
        "wrote": False,
        "idempotency_key": "K",
    }
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert replay.headers["Idempotency-Replayed"] == "1"
    assert rows.json()["rows"] == [{"x": 10}]


def test_idempotency_entry_expires_by_ttl(tmp_path: Path):
    with _client(
        {
            "ALLOW_WRITE_BACK": "1",
            "CACHE_DB_PATH": "idem-c.db",
            "GOOGLE_SHEET_ID": "test",
            "IDEMPOTENCY_TTL_SECONDS": "1",
        },
        tmp_path,
    ) as client:
        first = client.post(
            "/append",
            headers={
                "Authorization": "Bearer dev_token",
                "Idempotency-Key": "EXPIRE",
            },
            json={"x": 20},
        )

        with Session(store.engine) as session:
            row = session.get(store.Idempotency, "EXPIRE")
            row.created_at = 0
            session.add(row)
            session.commit()

        replay = client.post(
            "/append",
            headers={
                "Authorization": "Bearer dev_token",
                "Idempotency-Key": "EXPIRE",
            },
            json={"x": 21},
        )
        rows = client.get("/rows")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.headers.get("Idempotency-Replayed") is None
    assert replay.json() == {
        "inserted": 1,
        "wrote": False,
        "idempotency_key": "EXPIRE",
    }
    assert rows.json()["rows"] == [{"x": 20}, {"x": 21}]
