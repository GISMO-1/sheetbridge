# SheetBridge
Expose a Google Sheet as a REST API with OpenAPI and optional write-back.

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn sheetbridge.main:app --reload
```
Open http://127.0.0.1:8000/docs

## What's in this repo?
- Python 3.11 project packaged as `sheetbridge` with install metadata in `pyproject.toml` at the repo root.
- FastAPI app entry point: `sheetbridge/main.py` (exports `app`).
- Tests live in `tests/`; run with `pytest -q`.
- CI pipeline: `.github/workflows/ci.yml` sets up Python 3.11, installs `.[dev]`, and runs pytest on pushes/PRs.

## Development notes
- Local database cache lives at `sheetbridge.db`; configure via environment (see `sheetbridge/config.py`).
- Environment variables can be loaded from `.env`.
- To install dev tooling without editable mode: `pip install -e ".[dev]"` after activating a Python 3.11 virtualenv.
- Linting is configured with Ruff (see `pyproject.toml`).

## Google Auth
- Service account: set `GOOGLE_SERVICE_ACCOUNT_JSON` to the JSON string. Optionally set `DELEGATED_SUBJECT` for domain-wide delegation.
- User OAuth: store the client secrets file on disk and set `GOOGLE_OAUTH_CLIENT_SECRETS=/workspace/client_secrets.json`. The first `GET /sync` run will walk through the console/device flow.
- Tokens persist at `TOKEN_STORE` (defaults to `.tokens/sheets.json`).
- Call `GET /sync` to ingest rows from the Sheet into SQLite or enable the background scheduler (`SYNC_ENABLED=1`).

## Background sync
- Disabled by default; set `SYNC_ENABLED=1` to launch the periodic fetcher at startup.
- Tune cadence with `SYNC_INTERVAL_SECONDS`, `SYNC_JITTER_SECONDS`, and `SYNC_BACKOFF_MAX_SECONDS` for exponential backoff ceiling.
- `/sync` remains available for on-demand refreshes.
- Inspect scheduler state via `GET /sync/status` (running flag, last run timestamps, error counters, and current config knobs).

## Write-back
- Enable write-back by setting `ALLOW_WRITE_BACK=1` (or `true`) and calling the authenticated `POST /append` endpoint with the bearer token defined by `API_TOKEN`.
- Requests are cached immediately via SQLite; if Google credentials with write scope are unavailable the API responds with `{"inserted": 1, "wrote": False}` and will not attempt the remote append.
- Provide write credentials via either a service account (`GOOGLE_SERVICE_ACCOUNT_JSON` + optional `DELEGATED_SUBJECT`) or user OAuth (`GOOGLE_OAUTH_CLIENT_SECRETS` + token flow). When credentials resolve successfully, `/append` issues a Sheets `values.append` call ordered by the header row and responds with `{"inserted": 1, "wrote": True}`.
