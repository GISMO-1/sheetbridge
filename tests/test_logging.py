from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sheetbridge.logging import AccessLogMiddleware


def test_request_id_header_on_error() -> None:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.headers["X-Request-ID"]
