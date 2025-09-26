"""Prometheus metrics registry and instrumentation helpers."""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

REGISTRY = CollectorRegistry()
REQUEST_COUNTER = Counter(
    "sb_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)
ERROR_COUNTER = Counter(
    "sb_errors_total",
    "HTTP 5xx responses",
    ["path"],
    registry=REGISTRY,
)
LATENCY_HISTOGRAM = Histogram(
    "sb_request_latency_seconds",
    "Request latency in seconds",
    ["method", "path"],
    registry=REGISTRY,
)


def metrics_response() -> Response:
    """Return a Response containing the latest metrics snapshot."""

    payload = generate_latest(REGISTRY)
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


class MetricsHook:
    """Track request latency, counts, and error totals."""

    async def before(self, method: str, path: str) -> float:
        return time.time()

    async def after(self, method: str, path: str, status: int, start: float) -> None:
        duration = max(0.0, time.time() - start)
        LATENCY_HISTOGRAM.labels(method, path).observe(duration)
        REQUEST_COUNTER.labels(method, path, str(status)).inc()
        if status >= 500:
            ERROR_COUNTER.labels(path).inc()
