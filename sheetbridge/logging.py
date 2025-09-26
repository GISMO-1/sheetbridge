"""Request logging middleware emitting JSON records with request IDs."""

from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.requests import Request
from starlette.responses import Response

SENSITIVE_HEADERS = {"authorization"}


def _req_id(req: Request) -> str:
    """Return the inbound request ID or generate a UUID4."""

    return req.headers.get("x-request-id") or str(uuid.uuid4())


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive headers from the emitted log payload."""

    return {
        key: ("<redacted>" if key.lower() in SENSITIVE_HEADERS else value)
        for key, value in headers.items()
    }


_REQUEST_ID_SCOPE_KEY = "sheetbridge.request_id"


_SERVER_ERROR_PATCHED = False


def _patch_server_error_middleware() -> None:
    """Ensure Starlette's server error middleware propagates request IDs."""

    original_call = ServerErrorMiddleware.__call__

    async def _patched_call(self, scope, receive, send):  # type: ignore[override]
        if scope.get("type") != "http":
            await original_call(self, scope, receive, send)
            return

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                request_id = scope.get(_REQUEST_ID_SCOPE_KEY)
                if request_id and "x-request-id" not in headers:
                    headers["X-Request-ID"] = request_id
                message = dict(message)
                message["headers"] = headers.raw
            await send(message)

        await original_call(self, scope, receive, _send)

    global _SERVER_ERROR_PATCHED
    if _SERVER_ERROR_PATCHED:
        return

    ServerErrorMiddleware.__call__ = _patched_call  # type: ignore[assignment]
    _SERVER_ERROR_PATCHED = True


_patch_server_error_middleware()


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit a JSON access log per request and ensure `X-Request-ID` headers."""

    async def dispatch(self, request: Request, call_next: Callable):  # type: ignore[override]
        request_id = _req_id(request)
        start = time.time()
        status = 500
        error: str | None = None
        response: Response | None = None
        request.scope[_REQUEST_ID_SCOPE_KEY] = request_id
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception as exc:  # pragma: no cover - handled after logging
            error = repr(exc)
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            record = {
                "ts": int(time.time()),
                "level": "ERROR" if error else "INFO",
                "msg": "access",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "status": status,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else None,
                "headers": _redact_headers(
                    {
                        key: value
                        for key, value in request.headers.items()
                        if key.lower() in {"authorization", "user-agent"}
                    }
                ),
            }
            if error:
                record["error"] = error
            print(json.dumps(record), flush=True)
            if response is not None:
                response.headers["X-Request-ID"] = request_id
