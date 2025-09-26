# HANDOFF
Status: Background sync scheduler remains available and disabled by default until credentials arrive. `/append` now supports idempotent writes backed by SQLite with a configurable TTL, cached responses, replay signalling, and an authenticated purge endpoint.

Next:
1. Supply Google read credentials and flip `SYNC_ENABLED=1` when ready to let the scheduler hydrate the cache automatically.
2. Decide on an appropriate `IDEMPOTENCY_TTL_SECONDS` for production retry behaviour and configure purge cadence (either via `/admin/idempotency/purge` or a scheduled job).
3. Monitor `/sync/status` after enabling to confirm runs, and keep an eye on the idempotency table size if retry volume is high.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py` (`/append` idempotency handling + admin purge)
- Scheduler module: `sheetbridge/scheduler.py`
- Store + idempotency helpers: `sheetbridge/store.py`
- Tests: `tests/` (see new `test_idempotency.py`)
- CI workflow: `.github/workflows/ci.yml`

Env:
- Python 3.11 virtualenv (`python -m venv .venv && source .venv/bin/activate`)
- Install dependencies with `pip install -e ".[dev]"`
- Configure settings via environment variables or `.env`
- New/updated config knobs: `SYNC_ENABLED` (defaults to `0`), `SYNC_INTERVAL_SECONDS` (default `300`), `SYNC_JITTER_SECONDS` (default `15`), `SYNC_BACKOFF_MAX_SECONDS` (default `600`), `IDEMPOTENCY_TTL_SECONDS` (default `86400`). Legacy knobs like `GOOGLE_OAUTH_CLIENT_SECRETS`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DELEGATED_SUBJECT`, `TOKEN_STORE`, and `ALLOW_WRITE_BACK` remain.

Scheduler snapshot:
- Enabled: false (default)
- Last started/finished: None (no runs while disabled)
- Counters: `total_runs=0`, `total_errors=0`
- Endpoint: `GET /sync/status`

Tests:
- `pytest -q`
- `tests/test_idempotency.py` covers retry caching, replay headers, and TTL expiry logic.

Google Auth handoff:
- Method configured: not configured (no credentials committed).
- Secrets paths: expected client secrets path via `GOOGLE_OAUTH_CLIENT_SECRETS`; service account via `GOOGLE_SERVICE_ACCOUNT_JSON` (string env). Token store defaults to `.tokens/sheets.json`.
- Last `/sync`: not run automatically; manual `/sync` still requires credentials and returns 503 until configured.
- Next auth step: provide credentials and enable background sync once ready.
