# HANDOFF
Status: Background sync scheduler remains available and disabled by default until credentials arrive. FastAPI startup now invokes `sheetbridge.config.reload_settings()` so each lifespan reload picks up env overrides before touching the cache or schema and rebuilds the SQLite engine via `sheetbridge.store.refresh_engine()` before migrations run. `/append` retains idempotent writes backed by SQLite with configurable TTL + purge endpoint, enforces schema contracts with coercion + required-field checks, and now performs deterministic cache upserts whenever `KEY_COLUMN` is configured so duplicate keys refresh existing rows instead of creating new ones. Contract violations or missing keys (when `UPSERT_STRICT` is enabled) return HTTP 422 and are persisted to the dead-letter queue. `/bulk/append` extends those semantics to batch ingestion, returning per-row success/failure alongside DLQ writes, respecting an optional batch idempotency key, honoring `BULK_MAX_ITEMS`, and chunking optional Google Sheets write-back via `SHEETS_BATCH_SIZE` when credentials permit. `/rows` continues to offer substring filtering, column projection, and a `since` cursor based on cache insertion time alongside pagination metadata. Structured JSON access logs emit per-request with request IDs, `/metrics` serves Prometheus counters/histograms, and an optional per-IP token bucket limiter can gate traffic. Admin maintenance endpoints require either the legacy bearer token or a configured API key via the shared `require_auth` helper, and CORS middleware respects the `CORS_ALLOW_ORIGINS` allow-list. `/admin/schema`, `/admin/dlq`, and the new `/admin/dupes` endpoint expose schema state, the dead-letter queue, and duplicate key diagnostics over authenticated calls. OpenAPI is now locked to `openapi.json`; regenerate via `python -m sheetbridge.openapi_tool --out openapi.json` (or `make schema`) and CI enforces drift with a deterministic spec generator.

Key upsert snapshot:
- `KEY_COLUMN`: unset (`None` by default; enable to deduplicate cache rows on `/append`).
- `UPSERT_STRICT`: `True` (default; rejects missing keys when a key column is active).
- Known duplicate rows: none detected (fresh cache during tests).

Next:
1. Coordinate client rollout for `/bulk/append`, monitor DLQ rejects, and tune `BULK_MAX_ITEMS`/`SHEETS_BATCH_SIZE` once real traffic patterns emerge.
2. Author and upload the canonical schema contract via `/admin/schema` (or ship `schema.json`) once downstream consumers finalize the column set; defaults remain permissive until then.
3. After API surface changes, run `make schema` (or `python -m sheetbridge.openapi_tool --out openapi.json`) and commit the refreshed `openapi.json` to keep CI green.
4. Decide on and configure `KEY_COLUMN` when ready to deduplicate cache rows, then monitor `/admin/dupes` for anomalies once enabled.
5. Supply Google read credentials and flip `SYNC_ENABLED=1` when ready to let the scheduler hydrate the cache automatically.
6. Populate `API_KEYS` with one or more secrets and narrow `CORS_ALLOW_ORIGINS` to trusted origins before exposing admin tooling.
7. Consider surfacing real Sheet update timestamps to replace the current cache-created `since` filter approximation.
8. Decide on an appropriate `IDEMPOTENCY_TTL_SECONDS` for production retry behaviour and configure purge cadence (either via `/admin/idempotency/purge` or a scheduled job).
9. Monitor `/sync/status` after enabling to confirm runs, keep an eye on the idempotency table size if retry volume is high, review `/admin/dlq` regularly for schema rejects, and audit `/admin/dupes` if a key column is active.

Paths:
- Application package: `sheetbridge/`
- Entrypoint: `sheetbridge/main.py` (`/rows` filters, `/append` idempotency handling + admin purge, logging/metrics wiring, rate limiting gate)
- Logging middleware: `sheetbridge/logging.py`
- Metrics registry + hooks: `sheetbridge/metrics.py`
- Rate limiter: `sheetbridge/ratelimit.py`
- Scheduler module: `sheetbridge/scheduler.py`
- Store + idempotency helpers: `sheetbridge/store.py` (rows cache records `created_at` timestamps, exposes `insert_rows`/`query_rows`, now lazily rebuilds the SQLite engine per `CACHE_DB_PATH`, and handles key-based upserts + duplicate lookups)
- Schema contract loader + saver: `sheetbridge/schema.py`
- Validation + coercion utilities: `sheetbridge/validate.py`
- Store + idempotency + DLQ helpers: `sheetbridge/store.py` (rows cache records `created_at`, performs key-based upserts, exposes `insert_rows`/`query_rows`, tracks idempotency responses, and persists dead-letter rows)
- Package init: `sheetbridge/__init__.py` lazily resolves `app` to avoid config validation before envs are set (needed for the OpenAPI tooling).
- OpenAPI lock + CLI: `sheetbridge/openapi_tool.py`, generated `openapi.json`, and `Makefile` targets `schema` / `schema-check`.
- Tests: `tests/` (includes `test_rows_filters.py`, `test_idempotency.py`, `test_metrics_ratelimit.py`, and `test_auth_security.py`)
- CI workflow: `.github/workflows/ci.yml`

Implementation notes:
- `Row.created_at` captures the cache insertion second for each batch of inserted rows; `/rows?since=` comparisons currently use this timestamp as a proxy for freshness.
- `init_db()` now runs a lightweight SQLite migration to add and backfill the `created_at` column on legacy cache databases so upgrades do not require manual rebuilds.
- `query_rows` filters substring matches by casting the JSON payload to text and applying a `LOWER(...) LIKE %query%` check. SQLite handles this via its `TEXT` representation; if we move to a database without JSON casting support we may need a dedicated search strategy. Key-based upserts reuse the same table and refresh `created_at` whenever an existing key is updated.
- `sheetbridge/schema.py` caches the most recently loaded contract path/content; startup loads `settings.SCHEMA_JSON_PATH` when present and `POST /admin/schema` persists + reloads the JSON file so subsequent requests see the new contract immediately.
- `validate_row` coerce functions accept string/number/integer/boolean/datetime/date column types, normalize datetime-like values back to ISO 8601 strings for JSON storage, and gracefully pass through extra keys. Missing required fields or conversion failures short-circuit with a reason string recorded in the dead-letter queue.
- `/bulk/append` iterates the same validation pipeline per row, drops strict key misses before hitting the cache when `UPSERT_STRICT` is true, preserves per-row indices in the response, and stores partial success responses under batch idempotency keys without rolling back successful inserts.
- Dead-letter rows are stored via the new `DeadLetter` SQLModel table with `reason`, original `data`, and a `created_at` timestamp to support future replay/inspection.
- Access logging prints JSON objects with fields: `ts`, `level`, `msg`, `request_id`, `method`, `path`, `query`, `status`, `duration_ms`, `client_ip`, optional `error`, and redacted header echoes. The middleware always attaches an `X-Request-ID` response header, even when a route raises and returns a `500` from the server error handler.
- Error handling: Access logging no longer consumes exceptions—it records them, lets FastAPI/Starlette's handlers run (preserving custom `exception_handler` hooks and debug tracebacks), and monkey patches `ServerErrorMiddleware` in-process so the generated fallback response also carries the captured request ID.
- Prometheus metrics include `sb_requests_total{method,path,status}`, `sb_request_latency_seconds{method,path}`, and `sb_errors_total{path}`. `/metrics` returns the standard text exposition format.
- Token bucket rate limiting is disabled by default; enable by toggling `RATE_LIMIT_ENABLED` and tuning `RATE_LIMIT_RPS` + `RATE_LIMIT_BURST`. Buckets are keyed by client IP.
- Future enhancement: persist upstream Sheet update timestamps or per-row hashes to make `since` filtering reflect actual Sheet edits rather than cache time.
- `require_auth` now guards `/admin/*`, allowing the legacy bearer token (`Authorization: Bearer <API_TOKEN>`; defaults to `dev_token` unless you override the value) or any key from the comma-separated `API_KEYS` list via the `X-API-Key` header. `require_write_token` reuses the same bearer/key checks so `/append` and `/rows` writes can authenticate with either credential. `/admin/dupes` shares the same guard and surfaces keys with duplicate cached rows when a key column is configured.
- `sheetbridge.openapi_tool` bootstraps the FastAPI app with a stub `GOOGLE_SHEET_ID`, serializes the schema with stable sorting/indentation, and either rewrites or verifies `openapi.json`; `sheetbridge/__init__.py` now defers importing `sheetbridge.main` until `app` is accessed so the CLI can run without configuring the full environment first.

Env:
- Python 3.11 virtualenv (`python -m venv .venv && source .venv/bin/activate`)
- Install dependencies with `pip install -e ".[dev]"` (dev extra pins `httpx>=0.27,<1.0` so the Starlette TestClient dependency lands during setup)
- Configure settings via environment variables or `.env`
- New/updated config knobs: `API_KEYS` (comma-separated admin API keys, default empty), `CORS_ALLOW_ORIGINS` (comma-separated origins, default `*`), `SYNC_ENABLED` (defaults to `0`), `SYNC_INTERVAL_SECONDS` (default `300`), `SYNC_JITTER_SECONDS` (default `15`), `SYNC_BACKOFF_MAX_SECONDS` (default `600`), `IDEMPOTENCY_TTL_SECONDS` (default `86400`), `LOG_LEVEL` (default `INFO`), `RATE_LIMIT_ENABLED` (default `0`), `RATE_LIMIT_RPS` (default `5.0`), `RATE_LIMIT_BURST` (default `20`), `SCHEMA_JSON_PATH` (default `schema.json`, optional), `KEY_COLUMN` (default unset/`None`), `UPSERT_STRICT` (default `1`/`True`, toggles rejection of missing keys when a key column is active), `BULK_MAX_ITEMS` (default `500`, caps `/bulk/append` payload size), and `SHEETS_BATCH_SIZE` (default `200`, controls write-back chunking). Legacy knobs like `GOOGLE_OAUTH_CLIENT_SECRETS`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `DELEGATED_SUBJECT`, `TOKEN_STORE`, and `ALLOW_WRITE_BACK` remain.

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
- `tests/test_schema_contracts.py` exercises `/admin/schema`, `/admin/dlq`, schema persistence, type/required-field validation, and cache writes for valid rows.
- `tests/test_key_upsert.py` validates deterministic upsert behaviour, strict key enforcement, and the duplicate inspection endpoint.
- `tests/test_bulk_append.py` covers partial success handling, batch idempotency, and payload limit enforcement for `/bulk/append`.
- `tests/test_openapi_lock.py` ensures the OpenAPI generator is deterministic and emits a 3.x schema; pair with `python -m sheetbridge.openapi_tool --check --out openapi.json` (or `make schema-check`) in CI/local workflows.

Schema & DLQ snapshot:
- Current schema path: `settings.SCHEMA_JSON_PATH` (defaults to `schema.json` in the repo root). No schema file ships by default, so the contract is unset until created via `/admin/schema`.
- Primary key column: unset (`settings.KEY_COLUMN is None`). Configure when you are ready to deduplicate cache rows on `/append`; toggle `UPSERT_STRICT` to reject missing keys and review `/admin/dupes` for anomalies once enabled.
- Dead-letter queue: persisted in SQLite table `deadletter` (via `sheetbridge/store.py`). Entries include `reason`, the original payload, and a unix `created_at` timestamp. Access via authenticated `GET /admin/dlq`.

Google Auth handoff:
- Method configured: not configured (no credentials committed).
- Secrets paths: expected client secrets path via `GOOGLE_OAUTH_CLIENT_SECRETS`; service account via `GOOGLE_SERVICE_ACCOUNT_JSON` (string env). Token store defaults to `.tokens/sheets.json`.
- Last `/sync`: not run automatically; manual `/sync` still requires credentials and returns 503 until configured.
- Next auth step: provide credentials and enable background sync once ready.
