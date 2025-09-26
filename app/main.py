from fastapi import FastAPI, Depends, Body, Query
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
from .config import settings
from .store import init_db, upsert_rows, list_rows
from .auth import require_write_token

app = FastAPI(title="SheetBridge", version="0.1.0")

class Health(BaseModel):
    status: str
    time: str

@app.on_event("startup")
def boot():
    Path(settings.CACHE_DB_PATH).touch(exist_ok=True)
    init_db()

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
