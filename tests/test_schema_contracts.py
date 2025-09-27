import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet")
os.environ.setdefault("CACHE_DB_PATH", "test-schema.db")

from sheetbridge.config import settings
from sheetbridge.main import app


@pytest.fixture()
def client(tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    db_path = tmp_path / "cache.db"
    env = {
        "ALLOW_WRITE_BACK": "1",
        "CACHE_DB_PATH": str(db_path),
        "GOOGLE_SHEET_ID": "test-sheet",
        "SCHEMA_JSON_PATH": str(schema_path),
        "KEY_COLUMN": "id",
    }
    original_attrs = {key: getattr(settings, key) for key in env if hasattr(settings, key)}
    for key, value in env.items():
        os.environ[key] = value
        if key == "ALLOW_WRITE_BACK":
            setattr(settings, key, True)
        else:
            setattr(settings, key, value)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in env.items():
            os.environ.pop(key, None)
        for key, value in original_attrs.items():
            setattr(settings, key, value)
        if db_path.exists():
            db_path.unlink()
        if schema_path.exists():
            schema_path.unlink()


def _auth_headers():
    return {"Authorization": "Bearer dev_token"}


def test_schema_contract_validation_and_dlq(client: TestClient, tmp_path: Path):
    contract = {
        "columns": {
            "id": {"type": "string", "required": True},
            "amount": {"type": "integer"},
        }
    }
    response = client.post("/admin/schema", json=contract, headers=_auth_headers())
    assert response.status_code == 200
    schema_file = Path(settings.SCHEMA_JSON_PATH)
    assert schema_file.exists()
    with schema_file.open("r", encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored == contract

    response = client.get("/admin/schema", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json() == contract

    response = client.post(
        "/append",
        headers=_auth_headers(),
        json={"amount": 5},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid", "reason": "missing_required:id"}

    dlq_response = client.get("/admin/dlq", headers=_auth_headers())
    items = dlq_response.json()["items"]
    assert len(items) == 1
    assert items[0]["reason"] == "missing_required:id"

    response = client.post(
        "/append",
        headers=_auth_headers(),
        json={"id": "abc", "amount": "oops"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid", "reason": "type_error:amount:integer"}

    dlq_response = client.get("/admin/dlq", headers=_auth_headers())
    items = dlq_response.json()["items"]
    assert len(items) == 2
    assert items[0]["reason"] == "type_error:amount:integer"

    response = client.post(
        "/append",
        headers=_auth_headers(),
        json={"id": "xyz", "amount": 7},
    )
    assert response.status_code == 200
    assert response.json()["inserted"] == 1

    rows_response = client.get("/rows")
    rows = rows_response.json()["rows"]
    assert rows == [{"id": "xyz", "amount": 7}]

    dlq_response = client.get("/admin/dlq", headers=_auth_headers())
    assert len(dlq_response.json()["items"]) == 2
