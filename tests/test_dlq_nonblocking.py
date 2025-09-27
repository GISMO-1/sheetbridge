from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from sheetbridge.main import app
from sheetbridge.store import dlq_write


def _client(tmp: Path) -> TestClient:
    os.environ.update(
        {
            "CACHE_DB_PATH": str(tmp / "t.db"),
            "GOOGLE_SHEET_ID": "t",
            "API_KEYS": "k1",
            "DLQ_RETRY_ENABLED": "1",
            "DLQ_RETRY_INTERVAL": "1",
            "DLQ_RETRY_BATCH": "5",
            "DLQ_RETRY_CONCURRENCY": "2",
        }
    )
    return TestClient(app)


def test_requests_remain_responsive(tmp_path: Path, monkeypatch):
    import time as _t
    from sheetbridge import main as M

    def slow_append(creds, row):
        _t.sleep(0.25)

    monkeypatch.setattr(M, "append_row", slow_append, raising=True)

    client = _client(tmp_path)
    for i in range(6):
        dlq_write("write_failed", {"id": str(i)})

    start = time.time()
    response = client.get("/health", headers={"X-API-Key": "k1"})
    latency = time.time() - start

    assert response.status_code == 200
    assert latency < 0.2
