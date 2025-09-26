# HANDOFF
Status: FastAPI MVP exposes `/health`, `/rows` (GET/POST). Packaging renamed to `sheetbridge/` with editable installs working from repo root. Sheets OAuth still pending.

Next:
1. Wire Google OAuth device flow and/or service accounts.
2. Schedule periodic Sheet → SQLite sync via APScheduler.
3. Implement append write-back to Google Sheets.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py`
- Tests: `tests/`
- CI workflow: `.github/workflows/ci.yml`

Env:
- Python 3.11 virtualenv (`python -m venv .venv && source .venv/bin/activate`)
- Install dependencies with `pip install -e ".[dev]"`
- Configure settings via environment variables or `.env`

Tests:
- `pytest -q`
