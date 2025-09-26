# HANDOFF
Status: Read sync works and write-back append endpoint now caches rows locally and conditionally writes to Google Sheets when write credentials resolve. Config exposes ALLOW_WRITE_BACK to gate the new behavior.

Next:
1. Wire a scheduler or background job for periodic sync/flush once append behavior is validated.
2. Harden error handling/logging around credential refresh and append failures.
3. Explore retry/backoff strategies for write-back when Sheets APIs fail.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py`
- Tests: `tests/`
- CI workflow: `.github/workflows/ci.yml`

Env:
- Python 3.11 virtualenv (`python -m venv .venv && source .venv/bin/activate`)
- Install dependencies with `pip install -e ".[dev]"`
- Configure settings via environment variables or `.env`
- New config knobs: `GOOGLE_OAUTH_CLIENT_SECRETS`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DELEGATED_SUBJECT`, `TOKEN_STORE` (defaults to `.tokens/sheets.json`), `SYNC_ON_START` (defaults to `0`), `ALLOW_WRITE_BACK` (defaults to `0`).

Tests:
- `pytest -q`

Google Auth handoff:
- Method configured: not configured (no credentials committed).
- Secrets paths: expected client secrets path via `GOOGLE_OAUTH_CLIENT_SECRETS`; service account via `GOOGLE_SERVICE_ACCOUNT_JSON` (string env). Token store defaults to `.tokens/sheets.json`.
- Last `/sync`: not run (no creds); endpoint returns 503 until configured.
- Next auth step: schedule background sync/append flush once write credentials are configured.
