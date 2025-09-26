# SheetBridge
Expose a Google Sheet as a REST API with OpenAPI and optional write-back.

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
Open http://127.0.0.1:8000/docs
