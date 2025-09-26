# HANDOFF
Status: Google credential plumbing landed. Config now supports service accounts or OAuth device flow, `/sync` endpoint ingests rows into SQLite, and optional startup sync is available but disabled by default.

Next:
1. Enable write scope + append integration for Task 3.
2. Consider background scheduler once Task 3 confirms manual sync behavior.
3. Harden error handling/logging around credential refresh.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py`
- Tests: `tests/`
- CI workflow: `.github/workflows/ci.yml`

Env:
- Python 3.11 virtualenv (`python -m venv .venv && source .venv/bin/activate`)
- Install dependencies with `pip install -e ".[dev]"`
- Configure settings via environment variables or `.env`
- New config knobs: `GOOGLE_OAUTH_CLIENT_SECRETS`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DELEGATED_SUBJECT`, `TOKEN_STORE` (defaults to `.tokens/sheets.json`), `SYNC_ON_START` (defaults to `0`).

Tests:
- `pytest -q`

Google Auth handoff:
- Method configured: not configured (no credentials committed).
- Secrets paths: expected client secrets path via `GOOGLE_OAUTH_CLIENT_SECRETS`; service account via `GOOGLE_SERVICE_ACCOUNT_JSON` (string env). Token store defaults to `.tokens/sheets.json`.
- Last `/sync`: not run (no creds); endpoint returns 503 until configured.
- Next auth step: expand scopes to allow append/write in Task 3.
