from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Header,
    Response,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import schema as schema_mod
from .auth import require_auth, require_write_token
from .config import settings, reload_settings
from .logging_setup import RequestLogMiddleware, init_logging
from .metrics import LAT, REQS, router as metrics_router
from .oauth import resolve_credentials
from .ratelimit import allow
from .scheduler import retry_dlq, run_periodic, state as sync_state
from .sheets import append_row, append_rows, fetch_sheet
from .store import (
    dlq_delete,
    dlq_fetch,
    dlq_list,
    dlq_write,
    find_duplicates,
    get_idempotency,
    init_db,
    insert_rows,
    purge_idempotency_older_than,
    refresh_engine,
    query_rows,
    save_idempotency,
    upsert_by_key,
    upsert_by_key_bulk,
    upsert_rows,
    upsert_rows_bulk,
)
from .validate import validate_row


class Health(BaseModel):
    status: str
    time: str


def _sync_once_sync() -> int:
    creds = resolve_credentials(
        settings.GOOGLE_OAUTH_CLIENT_SECRETS,
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        settings.DELEGATED_SUBJECT,
        settings.TOKEN_STORE,
        scope="read",
    )
    if not creds:
        raise RuntimeError("Google credentials not configured")
    rows = fetch_sheet(creds)
    insert_rows(rows)
    return len(rows)


async def _sync_once() -> None:
    await asyncio.to_thread(_sync_once_sync)


@asynccontextmanager
async def lifespan(app: FastAPI):
    reload_settings()
    refresh_engine()
    Path(settings.CACHE_DB_PATH).touch(exist_ok=True)
    init_db()
    schema_mod.load(getattr(settings, "SCHEMA_JSON_PATH", "schema.json"))
    tasks: list[asyncio.Task[None]] = []
    if bool(getattr(settings, "SYNC_ENABLED", False)):
        async def loop() -> None:
            await run_periodic(
                _sync_once,
                settings.SYNC_INTERVAL_SECONDS,
                settings.SYNC_JITTER_SECONDS,
                settings.SYNC_BACKOFF_MAX_SECONDS,
            )

        tasks.append(asyncio.create_task(loop()))

    if bool(getattr(settings, "DLQ_RETRY_ENABLED", True)):
        def _retry_one_sync(row):
            creds = resolve_credentials(
                settings.GOOGLE_OAUTH_CLIENT_SECRETS,
                settings.GOOGLE_SERVICE_ACCOUNT_JSON,
                settings.DELEGATED_SUBJECT,
                settings.TOKEN_STORE,
                scope="write",
            )
            if not creds:
                raise RuntimeError("no creds")
            append_row(creds, row.data)

        tasks.append(
            asyncio.create_task(
                retry_dlq(
                    _retry_one_sync,
                    int(getattr(settings, "DLQ_RETRY_INTERVAL", 300)),
                    int(getattr(settings, "DLQ_RETRY_BATCH", 50)),
                    int(getattr(settings, "DLQ_RETRY_CONCURRENCY", 4)),
                )
            )
        )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task


init_logging(settings.LOG_LEVEL)

app = FastAPI(title="SheetBridge", version="0.3.0", lifespan=lifespan)
app.add_middleware(RequestLogMiddleware)
app.include_router(metrics_router())

origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _metrics_and_rate(request: Request, call_next):
    method = request.method
    path = request.url.path
    start = time.time()
    status_code = 500
    try:
        if getattr(settings, "RATE_LIMIT_ENABLED", False):
            client_host = request.client.host if request.client else "unknown"
            allowed = allow(
                client_host,
                float(getattr(settings, "RATE_LIMIT_RPS", 5.0)),
                int(getattr(settings, "RATE_LIMIT_BURST", 20)),
            )
            if not allowed:
                response = JSONResponse({"detail": "rate limit"}, status_code=429)
                status_code = response.status_code
                return response
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.time() - start
        REQS.labels(method, path, str(status_code)).inc()
        LAT.labels(method, path).observe(duration)


@app.get("/health", response_model=Health)
def health():
    return Health(status="ok", time=datetime.utcnow().isoformat())


@app.get("/rows")
def get_rows(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="substring filter"),
    columns: Optional[str] = Query(None, description="comma-separated projection"),
    since: Optional[str] = Query(None, description="ISO-8601 or unix seconds"),
):
    cols_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
    since_unix: Optional[int] = None
    if since:
        try:
            if since.isdigit():
                since_unix = int(since)
            else:
                from datetime import datetime, timezone

                parsed = datetime.fromisoformat(since)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                since_unix = int(parsed.timestamp())
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=400, detail="invalid 'since' value") from exc

    rows, total = query_rows(
        q=q,
        columns=cols_list,
        since_unix=since_unix,
        limit=limit,
        offset=offset,
    )
    return {"rows": rows, "total": total, "limit": limit, "offset": offset}


@app.post("/rows")
def add_row(row: dict = Body(...), _=Depends(require_write_token)):
    # For MVP we only cache; write-back to Sheet can be wired after OAuth is set up
    insert_rows([row])
    return {"inserted": 1}


@app.post("/append")
def append(
    response: Response,
    row: dict = Body(...),
    _=Depends(require_write_token),
    idem_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    ttl = getattr(settings, "IDEMPOTENCY_TTL_SECONDS", 86400)
    if idem_key:
        cached = get_idempotency(idem_key, ttl)
        if cached is not None:
            response.headers["Idempotency-Replayed"] = "1"
            return cached

    allow_write = str(getattr(settings, "ALLOW_WRITE_BACK", 0)).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    ok, cleaned, reason = validate_row(row)
    if not ok:
        dlq_write(reason or "invalid", row)
        response.status_code = 422
        return {"detail": "invalid", "reason": reason}

    key_column = getattr(settings, "KEY_COLUMN", None)
    stored = 0
    try:
        if key_column:
            stored = upsert_by_key(
                [cleaned], key_column, getattr(settings, "UPSERT_STRICT", True)
            )
        else:
            stored = upsert_rows([cleaned])
    except ValueError as exc:
        dlq_write(str(exc), row)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not allow_write:
        out = {"inserted": stored, "wrote": False, "idempotency_key": idem_key or None}
        if idem_key:
            save_idempotency(idem_key, out)
        response.status_code = 403
        return out
    row = cleaned
    creds = resolve_credentials(
        settings.GOOGLE_OAUTH_CLIENT_SECRETS,
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        settings.DELEGATED_SUBJECT,
        settings.TOKEN_STORE,
        scope="write",
    )
    if not creds:
        out = {"inserted": stored, "wrote": False, "idempotency_key": idem_key or None}
        if idem_key:
            save_idempotency(idem_key, out)
        return out

    try:
        append_row(creds, row)
    except Exception:  # noqa: BLE001
        dlq_write("write_failed", row)
        out = {"inserted": stored, "wrote": False, "idempotency_key": idem_key or None}
        if idem_key:
            save_idempotency(idem_key, out)
        return out

    out = {"inserted": stored, "wrote": True, "idempotency_key": idem_key or None}
    if idem_key:
        save_idempotency(idem_key, out)
    return out


@app.post("/bulk/append")
def bulk_append(
    response: Response,
    rows: List[dict] = Body(...),
    _=Depends(require_auth),
    idem_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="body must be a JSON array")
    if len(rows) > settings.BULK_MAX_ITEMS:
        raise HTTPException(status_code=413, detail="too many rows")

    ttl = settings.IDEMPOTENCY_TTL_SECONDS
    if idem_key:
        hit = get_idempotency(idem_key, ttl)
        if hit is not None:
            response.headers["Idempotency-Replayed"] = "1"
            return hit

    ok_rows: list[int] = []
    bad_rows: list[dict[str, object]] = []
    cleaned_rows: list[tuple[int, dict]] = []
    keyed_payload: list[dict] = []
    fallback_payload: list[dict] = []
    key_column = getattr(settings, "KEY_COLUMN", None)
    strict_keys = bool(getattr(settings, "UPSERT_STRICT", True))

    for idx, row in enumerate(rows):
        ok, cleaned, reason = validate_row(row)
        if not ok:
            bad_rows.append({"index": idx, "reason": reason})
            dlq_write(reason or "invalid", row)
            continue
        if key_column:
            key_value = cleaned.get(key_column)
            if key_value is None and strict_keys:
                reason = f"missing key:{key_column}"
                bad_rows.append({"index": idx, "reason": reason})
                dlq_write(reason, row)
                continue
            if key_value is None:
                fallback_payload.append(cleaned)
            else:
                keyed_payload.append(cleaned)
        else:
            fallback_payload.append(cleaned)
        cleaned_rows.append((idx, cleaned))
        ok_rows.append(idx)

    if cleaned_rows:
        if key_column:
            if keyed_payload:
                upsert_by_key_bulk(keyed_payload, key_column, strict_keys)
            if fallback_payload:
                upsert_rows_bulk(fallback_payload)
        else:
            upsert_rows_bulk(fallback_payload)

    wrote = False
    if bool(getattr(settings, "ALLOW_WRITE_BACK", False)) and cleaned_rows:
        creds = resolve_credentials(
            settings.GOOGLE_OAUTH_CLIENT_SECRETS,
            settings.GOOGLE_SERVICE_ACCOUNT_JSON,
            settings.DELEGATED_SUBJECT,
            settings.TOKEN_STORE,
            scope="write",
        )
        if creds:
            batch = [clean for _, clean in cleaned_rows]
            chunk_size = int(getattr(settings, "SHEETS_BATCH_SIZE", 200))
            success = False
            for start in range(0, len(batch), chunk_size):
                chunk = batch[start : start + chunk_size]
                try:
                    append_rows(creds, chunk)
                except Exception:  # noqa: BLE001
                    for failed in chunk:
                        dlq_write("write_failed", failed)
                    continue
                success = True
            wrote = success

    out = {
        "accepted": ok_rows,
        "rejected": bad_rows,
        "wrote": wrote,
        "count": len(cleaned_rows),
        "idempotency_key": idem_key,
    }
    if idem_key:
        save_idempotency(idem_key, out)
    return out


@app.get("/admin/dupes")
def admin_dupes(_=Depends(require_auth)):
    if not settings.KEY_COLUMN:
        return {"detail": "no key_column set"}
    return {"duplicates": find_duplicates(settings.KEY_COLUMN)}


@app.get("/admin/schema")
def admin_get_schema(_=Depends(require_auth)):
    contract = schema_mod.get()
    return schema_mod.to_payload(contract) if contract else {"columns": {}}


@app.post("/admin/schema")
def admin_set_schema(payload: dict, _=Depends(require_auth)):
    contract = schema_mod.Contract.model_validate(payload)
    path = schema_mod.save(contract, getattr(settings, "SCHEMA_JSON_PATH", "schema.json"))
    schema_mod.load(path)
    return {"saved": path}


@app.get("/admin/dlq")
def admin_list_dlq(limit: int = 100, offset: int = 0, _=Depends(require_auth)):
    return {"items": dlq_list(limit, offset)}


@app.post("/admin/dlq/retry")
def admin_retry_dlq(_=Depends(require_auth)):
    rows = dlq_fetch(50)
    retried: list[int] = []
    creds = resolve_credentials(
        settings.GOOGLE_OAUTH_CLIENT_SECRETS,
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        settings.DELEGATED_SUBJECT,
        settings.TOKEN_STORE,
        scope="write",
    )
    if not creds:
        raise HTTPException(status_code=503, detail="no creds")
    for row in rows:
        try:
            append_row(creds, row.data)
        except Exception:  # noqa: BLE001
            continue
        if row.id is not None:
            retried.append(row.id)
    if retried:
        dlq_delete(retried)
    return {"retried": len(retried)}


@app.post("/admin/idempotency/purge")
def purge_idempotency(_=Depends(require_auth)):
    purged = purge_idempotency_older_than(settings.IDEMPOTENCY_TTL_SECONDS)
    return {"purged": int(purged)}


@app.get("/sync")
def sync():
    try:
        synced = _sync_once_sync()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"synced": synced}


@app.get("/sync/status")
def sync_status():
    return {
        "running": sync_state.running,
        "last_started": sync_state.last_started,
        "last_finished": sync_state.last_finished,
        "last_error": sync_state.last_error,
        "total_runs": sync_state.total_runs,
        "total_errors": sync_state.total_errors,
        "enabled": bool(getattr(settings, "SYNC_ENABLED", False)),
        "interval": settings.SYNC_INTERVAL_SECONDS,
        "jitter": settings.SYNC_JITTER_SECONDS,
        "backoff_max": settings.SYNC_BACKOFF_MAX_SECONDS,
    }


