# HANDOFF
Status: Background sync scheduler remains available and disabled by default until credentials arrive. `/append` retains idempotent writes backed by SQLite with configurable TTL + purge endpoint. `/rows` now supports substring filtering, column projection, a `since` cursor based on cache insertion time, and reports `total/limit/offset` for pagination.

Next:
1. Supply Google read credentials and flip `SYNC_ENABLED=1` when ready to let the scheduler hydrate the cache automatically.
2. Consider surfacing real Sheet update timestamps to replace the current cache-created `since` filter approximation.
3. Decide on an appropriate `IDEMPOTENCY_TTL_SECONDS` for production retry behaviour and configure purge cadence (either via `/admin/idempotency/purge` or a scheduled job).
4. Monitor `/sync/status` after enabling to confirm runs, and keep an eye on the idempotency table size if retry volume is high.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py` (`/rows` filters, `/append` idempotency handling + admin purge)
- Scheduler module: `sheetbridge/scheduler.py`
- Store + idempotency helpers: `sheetbridge/store.py` (rows cache now records `created_at` timestamps, exposes `insert_rows` + `query_rows` helpers)
- Tests: `tests/` (includes `test_rows_filters.py` and `test_idempotency.py`)
- CI workflow: `.github/workflows/ci.yml`

Implementation notes:
- `Row.created_at` captures the cache insertion second for each batch of inserted rows; `/rows?since=` comparisons currently use this timestamp as a proxy for freshness.
- `query_rows` filters substring matches by casting the JSON payload to text and applying a `LOWER(...) LIKE %query%` check. SQLite handles this via its `TEXT` representation; if we move to a database without JSON casting support we may need a dedicated search strategy.
- Future enhancement: persist upstream Sheet update timestamps or per-row hashes to make `since` filtering reflect actual Sheet edits rather than cache time.

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
- `tests/test_rows_filters.py` exercises `/rows` projection, substring search, and `since` filtering.
- `tests/test_idempotency.py` covers retry caching, replay headers, and TTL expiry logic.

Google Auth handoff:
- Method configured: not configured (no credentials committed).
- Secrets paths: expected client secrets path via `GOOGLE_OAUTH_CLIENT_SECRETS`; service account via `GOOGLE_SERVICE_ACCOUNT_JSON` (string env). Token store defaults to `.tokens/sheets.json`.
- Last `/sync`: not run automatically; manual `/sync` still requires credentials and returns 503 until configured.
- Next auth step: provide credentials and enable background sync once ready.
