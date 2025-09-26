from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from .auth import require_write_token
from .config import settings
from .oauth import resolve_credentials
from .scheduler import run_periodic, state as sync_state
from .sheets import fetch_sheet
from .store import init_db, list_rows, upsert_rows


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
    upsert_rows(rows)
    return len(rows)


async def _sync_once() -> None:
    await asyncio.to_thread(_sync_once_sync)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.CACHE_DB_PATH).touch(exist_ok=True)
    init_db()
    task: Optional[asyncio.Task[None]] = None
    if bool(getattr(settings, "SYNC_ENABLED", False)):
        async def loop() -> None:
            await run_periodic(
                _sync_once,
                settings.SYNC_INTERVAL_SECONDS,
                settings.SYNC_JITTER_SECONDS,
                settings.SYNC_BACKOFF_MAX_SECONDS,
            )

        task = asyncio.create_task(loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task


app = FastAPI(title="SheetBridge", version="0.2.0", lifespan=lifespan)


@app.get("/health", response_model=Health)
def health():
    return Health(status="ok", time=datetime.utcnow().isoformat())


@app.get("/rows")
def get_rows(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    return {"rows": list_rows(limit=limit, offset=offset)}


@app.post("/rows")
def add_row(row: dict = Body(...), _=Depends(require_write_token)):
    # For MVP we only cache; write-back to Sheet can be wired after OAuth is set up
    upsert_rows([row])
    return {"inserted": 1}


@app.post("/append")
def append(row: dict = Body(...), _=Depends(require_write_token)):
    allow_write = str(getattr(settings, "ALLOW_WRITE_BACK", 0)).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not allow_write:
        raise HTTPException(status_code=403, detail="write-back disabled")
    upsert_rows([row])
    creds = resolve_credentials(
        settings.GOOGLE_OAUTH_CLIENT_SECRETS,
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        settings.DELEGATED_SUBJECT,
        settings.TOKEN_STORE,
        scope="write",
    )
    if not creds:
        return {"inserted": 1, "wrote": False}
    from .sheets import append_row

    append_row(creds, row)
    return {"inserted": 1, "wrote": True}


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
