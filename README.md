# SheetBridge
Expose a Google Sheet as a REST API with OpenAPI and optional write-back.

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn sheetbridge.main:app --reload
```
Open http://127.0.0.1:8000/docs

### Observability
- Structured logs with method, path, status, and latency emitted via the FastAPI middleware stack.
- Prometheus metrics exposed at `/metrics` ready for scraping.
- Core dependencies ship with `httpx>=0.27,<1.0` so Starlette's `TestClient` and async HTTP tooling are always available in local runs and CI.

### Schema locking
Generate or check the OpenAPI file pinned in this repo.

```bash
# regenerate
python -m sheetbridge.openapi_tool --out openapi.json

# CI-style check (fails on drift)
python -m sheetbridge.openapi_tool --check --out openapi.json
```

## What's in this repo?
- Python 3.11 project packaged as `sheetbridge` with install metadata in `pyproject.toml` at the repo root.
- FastAPI app entry point: `sheetbridge/main.py` (exports `app`).
- Tests live in `tests/`; run with `pytest -q`.
- CI pipeline: `.github/workflows/ci.yml` sets up Python 3.11, installs `.[dev]`, and runs pytest on pushes/PRs.

## Development notes
- Local database cache lives at `sheetbridge.db`; configure via environment (see `sheetbridge/config.py`).
- Environment variables can be loaded from `.env`.
- FastAPI lifespan now reloads configuration via `sheetbridge.config.reload_settings()` so env overrides set before startup (e.g. in tests) are respected on every app instance.
- Startup also rebuilds the SQLite engine through `sheetbridge.store.refresh_engine()` so per-test database paths and cache resets take effect immediately after env changes, and store helpers lazily reinitialize the schema for whichever SQLite file `settings.CACHE_DB_PATH` points to.
- To install dev tooling without editable mode: `pip install -e ".[dev]"` after activating a Python 3.11 virtualenv. The dev extra pins `httpx>=0.27,<1.0` so Starlette's `TestClient` works under pytest without manual installs.
- Linting is configured with Ruff (see `pyproject.toml`).
- `init_db()` automatically backfills the cached rows table with a `created_at` column if a legacy database is missing it, so `/rows?since=` continues working after upgrades without manual intervention.

## Logging, metrics, and rate limit
- `RequestLogMiddleware` writes structured INFO logs including method, path, HTTP status, and request latency in milliseconds.
- `/metrics` returns Prometheus exposition data with `sheetbridge_requests_total{method,path,status}` and `sheetbridge_latency_seconds{method,path}` for alerting/dashboards.
- Enable per-IP throttling by setting `RATE_LIMIT_ENABLED=1`. Tune the token bucket with `RATE_LIMIT_RPS` (refill rate) and `RATE_LIMIT_BURST` (bucket capacity). Defaults keep the limiter disabled.

### Filtering and projection
- `GET /rows?q=alice` → case-insensitive search across the JSON payload of each cached row.
- `GET /rows?columns=id,name` → return only those keys per row (projection happens after filtering and pagination).
- `GET /rows?since=2025-09-26T00:00:00Z` or `GET /rows?since=1696032000` → include rows with a cache timestamp greater than or equal to the supplied moment.
- Responses now include `total`, `limit`, and `offset` alongside the projected `rows` payload for pagination UX.

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
- `POST /append` and `POST /rows` now accept either the bearer token or any configured API key via `X-API-Key` for write access.
- Requests are cached immediately via SQLite; if Google credentials with write scope are unavailable the API responds with `{"inserted": 1, "wrote": False, "idempotency_key": null}` and will not attempt the remote append.
- Provide write credentials via either a service account (`GOOGLE_SERVICE_ACCOUNT_JSON` + optional `DELEGATED_SUBJECT`) or user OAuth (`GOOGLE_OAUTH_CLIENT_SECRETS` + token flow). When credentials resolve successfully, `/append` issues a Sheets `values.append` call ordered by the header row and responds with `{"inserted": 1, "wrote": True, "idempotency_key": null}` unless an idempotency key is supplied.

### Bulk append
- `POST /bulk/append` accepts an authenticated JSON array of rows (API key or bearer token) and reuses the same validation + key-upsert logic as `/append`.
- Each row is validated; the response includes `accepted` indices that made it through validation/upsert, alongside `rejected` entries with `{index, reason}` for DLQ triage. The endpoint never fails the whole batch if only a subset is invalid.
- Optional `Idempotency-Key` applies to the entire batch; retries replay the cached payload and add an `Idempotency-Replayed: 1` header.
- Cache writes happen immediately. When `ALLOW_WRITE_BACK=1` and credentials resolve, rows stream to Google Sheets in chunks controlled by `SHEETS_BATCH_SIZE` (default 200) so large batches respect the API append limits.
- Guard total payload size with `BULK_MAX_ITEMS` (default 500). Requests above the limit return HTTP 413 without touching the cache.

## Schema contracts and validation
- Configure `SCHEMA_JSON_PATH` (defaults to `schema.json`) to point at a JSON schema contract on disk. The schema is optional; when the file is absent payloads pass through unchanged.
- Manage the contract via the authenticated `GET /admin/schema` and `POST /admin/schema` endpoints. The POST handler persists the schema to disk and reloads it at runtime. Example payload:
  ```json
  {
    "columns": {
      "id": {"type": "string", "required": true},
      "name": {"type": "string"},
      "age": {"type": "integer"},
      "active": {"type": "boolean"}
    }
  }
  ```
- `/append` now validates incoming rows against the declared contract. Coercion handles strings, numbers, integers, booleans (`1/true/yes/y`), ISO datetime, and ISO date types. Datetime-like values are normalized back to ISO 8601 strings before caching so the JSON payload stays serializable. Missing required fields or type mismatches return HTTP 422 with details and land in the dead-letter queue (`GET /admin/dlq`).
- Optional primary key enforcement: set `KEY_COLUMN` to the column name to deduplicate cached rows on `/append`; pair with `UPSERT_STRICT` to reject payloads missing the key.

### Key-based upsert
Set `KEY_COLUMN=id` to deduplicate on that field.
- With `UPSERT_STRICT=1`, appends missing the key are rejected.
- With `UPSERT_STRICT=0`, rows missing the key still succeed but fall back to non-deduplicating inserts.
- Admin endpoint: `/admin/dupes` lists keys with >1 entry.

## Idempotency
- Use the optional `Idempotency-Key` header on `POST /append` calls to deduplicate retries. The first write stores the JSON response in the cache and subsequent calls with the same key return that payload verbatim with an extra `Idempotency-Replayed: 1` header.
- Every `/append` reply follows `{"inserted": 1, "wrote": <bool>, "idempotency_key": <string|null>}`; when idempotency is active the cached structure is reused.
- Entries expire based on `IDEMPOTENCY_TTL_SECONDS` (default 86,400 seconds). Override the environment variable to change the retention window.
- Run the authenticated `POST /admin/idempotency/purge` maintenance endpoint to delete expired entries immediately. The endpoint responds with `{"purged": <count>}` indicating how many records were removed. All `/admin/*` routes require either a legacy bearer token or a configured API key.

### Retry DLQ
- Failed Google Sheets writes are persisted to the dead-letter queue with reason `write_failed`.
- A background retry loop wakes every `DLQ_RETRY_INTERVAL` seconds (default 300) when `DLQ_RETRY_ENABLED=1`, fetches work in a thread (so SQLite access stays off the event loop), and replays up to `DLQ_RETRY_BATCH` entries using the configured write credentials.
- Each queued row now runs via a bounded worker pool controlled by `DLQ_RETRY_CONCURRENCY` (default `4`), keeping API handlers responsive even when Google Sheets writes block.
- Trigger manual retries on demand via authenticated `POST /admin/dlq/retry`; successful writes are removed from the queue and the response reports how many entries were retried.

### Authentication
- Bearer tokens (legacy, `Authorization: Bearer <API_TOKEN>`). The default token is `dev_token`; overriding `API_TOKEN` disables the dev token fallback unless you explicitly list `dev_token` in `API_KEYS`.
- API keys: set `API_KEYS` env var (comma-separated). Use header `X-API-Key: <key>`.

### CORS
Set `CORS_ALLOW_ORIGINS` to a comma list (`http://localhost:3000,http://example.com`).
