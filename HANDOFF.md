# HANDOFF
Status: Background sync scheduler remains available and disabled by default until credentials arrive. `/append` retains idempotent writes backed by SQLite with configurable TTL + purge endpoint. `/rows` now supports substring filtering, column projection, a `since` cursor based on cache insertion time, and reports `total/limit/offset` for pagination. Structured JSON access logs emit per-request with request IDs, `/metrics` serves Prometheus counters/histograms, and an optional per-IP token bucket limiter can gate traffic. Admin maintenance endpoints now require either the legacy bearer token or a configured API key via the shared `require_auth` helper, and CORS middleware respects the `CORS_ALLOW_ORIGINS` allow-list.

Next:
1. Supply Google read credentials and flip `SYNC_ENABLED=1` when ready to let the scheduler hydrate the cache automatically.
2. Populate `API_KEYS` with one or more secrets and narrow `CORS_ALLOW_ORIGINS` to trusted origins before exposing admin tooling.
3. Consider surfacing real Sheet update timestamps to replace the current cache-created `since` filter approximation.
4. Decide on an appropriate `IDEMPOTENCY_TTL_SECONDS` for production retry behaviour and configure purge cadence (either via `/admin/idempotency/purge` or a scheduled job).
5. Monitor `/sync/status` after enabling to confirm runs, and keep an eye on the idempotency table size if retry volume is high.
6. Wire observability sinks for the JSON logs and `/metrics` endpoint (e.g., ship to log aggregation + scrape Prometheus) and evaluate rate-limit thresholds before enabling in production.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py` (`/rows` filters, `/append` idempotency handling + admin purge, logging/metrics wiring, rate limiting gate)
- Logging middleware: `sheetbridge/logging.py`
- Metrics registry + hooks: `sheetbridge/metrics.py`
- Rate limiter: `sheetbridge/ratelimit.py`
- Scheduler module: `sheetbridge/scheduler.py`
- Store + idempotency helpers: `sheetbridge/store.py` (rows cache now records `created_at` timestamps, exposes `insert_rows` + `query_rows` helpers)
- Tests: `tests/` (includes `test_rows_filters.py`, `test_idempotency.py`, `test_metrics_ratelimit.py`, and `test_auth_security.py`)
- CI workflow: `.github/workflows/ci.yml`

Implementation notes:
- `Row.created_at` captures the cache insertion second for each batch of inserted rows; `/rows?since=` comparisons currently use this timestamp as a proxy for freshness.
- `init_db()` now runs a lightweight SQLite migration to add and backfill the `created_at` column on legacy cache databases so upgrades do not require manual rebuilds.
- `query_rows` filters substring matches by casting the JSON payload to text and applying a `LOWER(...) LIKE %query%` check. SQLite handles this via its `TEXT` representation; if we move to a database without JSON casting support we may need a dedicated search strategy.
- Access logging prints JSON objects with fields: `ts`, `level`, `msg`, `request_id`, `method`, `path`, `query`, `status`, `duration_ms`, `client_ip`, optional `error`, and redacted header echoes. The middleware always attaches an `X-Request-ID` response header, even when a route raises and returns a `500` from the server error handler.
- Error handling: Access logging no longer consumes exceptions—it records them, lets FastAPI/Starlette's handlers run (preserving custom `exception_handler` hooks and debug tracebacks), and monkey patches `ServerErrorMiddleware` in-process so the generated fallback response also carries the captured request ID.
- Prometheus metrics include `sb_requests_total{method,path,status}`, `sb_request_latency_seconds{method,path}`, and `sb_errors_total{path}`. `/metrics` returns the standard text exposition format.
- Token bucket rate limiting is disabled by default; enable by toggling `RATE_LIMIT_ENABLED` and tuning `RATE_LIMIT_RPS` + `RATE_LIMIT_BURST`. Buckets are keyed by client IP.
- Future enhancement: persist upstream Sheet update timestamps or per-row hashes to make `since` filtering reflect actual Sheet edits rather than cache time.
- `require_auth` now guards `/admin/*`, allowing the legacy bearer token (`Authorization: Bearer <API_TOKEN>`; defaults to `dev_token` unless you override the value) or any key from the comma-separated `API_KEYS` list via the `X-API-Key` header.

Env:
- Python 3.11 virtualenv (`python -m venv .venv && source .venv/bin/activate`)
- Install dependencies with `pip install -e ".[dev]"`
- Configure settings via environment variables or `.env`
- New/updated config knobs: `API_KEYS` (comma-separated admin API keys, default empty), `CORS_ALLOW_ORIGINS` (comma-separated origins, default `*`), `SYNC_ENABLED` (defaults to `0`), `SYNC_INTERVAL_SECONDS` (default `300`), `SYNC_JITTER_SECONDS` (default `15`), `SYNC_BACKOFF_MAX_SECONDS` (default `600`), `IDEMPOTENCY_TTL_SECONDS` (default `86400`), `LOG_LEVEL` (default `INFO`), `RATE_LIMIT_ENABLED` (default `0`), `RATE_LIMIT_RPS` (default `5.0`), `RATE_LIMIT_BURST` (default `20`). Legacy knobs like `GOOGLE_OAUTH_CLIENT_SECRETS`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DELEGATED_SUBJECT`, `TOKEN_STORE`, and `ALLOW_WRITE_BACK` remain.

Scheduler snapshot:
- Enabled: false (default)
- Last started/finished: None (no runs while disabled)
- Counters: `total_runs=0`, `total_errors=0`
- Endpoint: `GET /sync/status`

Tests:
- `pytest -q`
- `tests/test_rows_filters.py` exercises `/rows` projection, substring search, and `since` filtering.
- `tests/test_idempotency.py` covers retry caching, replay headers, and TTL expiry logic.
- `tests/test_metrics_ratelimit.py` validates the Prometheus endpoint and ensures the optional rate limiter can throttle bursts.
- `tests/test_auth_security.py` verifies `/admin/idempotency/purge` rejects unauthenticated calls and accepts valid API keys.

Google Auth handoff:
- Method configured: not configured (no credentials committed).
- Secrets paths: expected client secrets path via `GOOGLE_OAUTH_CLIENT_SECRETS`; service account via `GOOGLE_SERVICE_ACCOUNT_JSON` (string env). Token store defaults to `.tokens/sheets.json`.
- Last `/sync`: not run automatically; manual `/sync` still requires credentials and returns 503 until configured.
- Next auth step: provide credentials and enable background sync once ready.
