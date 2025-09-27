from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQS = Counter(
    "sheetbridge_requests_total",
    "Requests",
    ["method", "path", "status"],
)
LAT = Histogram(
    "sheetbridge_latency_seconds",
    "Latency",
    ["method", "path"],
)


def router() -> APIRouter:
    r = APIRouter()

    @r.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return r
