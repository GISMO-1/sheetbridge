from fastapi import Body, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
from .config import settings
from .oauth import resolve_credentials
from .sheets import fetch_sheet
from .store import init_db, list_rows, upsert_rows
from .auth import require_write_token

app = FastAPI(title="SheetBridge", version="0.1.0")

class Health(BaseModel):
    status: str
    time: str

@app.on_event("startup")
def boot():
    Path(settings.CACHE_DB_PATH).touch(exist_ok=True)
    init_db()
    if str(getattr(settings, "SYNC_ON_START", 0)) in {"1", "true", "True"}:
        try:
            sync()
        except Exception:
            pass

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
    creds = resolve_credentials(
        settings.GOOGLE_OAUTH_CLIENT_SECRETS,
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        settings.DELEGATED_SUBJECT,
        settings.TOKEN_STORE,
    )
    if not creds:
        raise HTTPException(status_code=503, detail="Google credentials not configured")
    rows = fetch_sheet(creds)
    upsert_rows(rows)
    return {"synced": len(rows)}
