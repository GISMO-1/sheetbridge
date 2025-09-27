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
- `init_db()` automatically backfills the cached rows table with a `created_at` column if a legacy database is missing it, so `/rows?since=` continues working after upgrades without manual intervention.

## Logging, request IDs, metrics, and rate limit
- Structured JSON logs now stream to stdout for every request via `AccessLogMiddleware`. Each entry includes latency, status, method, path, a redacted subset of headers, and a `request_id` field that echoes/sets the `X-Request-ID` header on responses, including `500` errors raised by routes.
- The middleware now lets exceptions bubble to Starlette's built-in handlers (so debug stack traces, custom `exception_handler(Exception)`, and `TestClient(raise_server_exceptions=True)` work again) while still stamping the fallback 500 produced by `ServerErrorMiddleware` with the originating request ID.
- A Prometheus endpoint lives at `GET /metrics` and exports `sb_requests_total`, `sb_request_latency_seconds`, and `sb_errors_total` sourced from in-process counters and histograms.
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
- Requests are cached immediately via SQLite; if Google credentials with write scope are unavailable the API responds with `{"inserted": 1, "wrote": False, "idempotency_key": null}` and will not attempt the remote append.
- Provide write credentials via either a service account (`GOOGLE_SERVICE_ACCOUNT_JSON` + optional `DELEGATED_SUBJECT`) or user OAuth (`GOOGLE_OAUTH_CLIENT_SECRETS` + token flow). When credentials resolve successfully, `/append` issues a Sheets `values.append` call ordered by the header row and responds with `{"inserted": 1, "wrote": True, "idempotency_key": null}` unless an idempotency key is supplied.

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
- `/append` now validates incoming rows against the declared contract. Coercion handles strings, numbers, integers, booleans (`1/true/yes/y`), ISO datetime, and ISO date types. Missing required fields or type mismatches return HTTP 422 with details and land in the dead-letter queue (`GET /admin/dlq`).
- Optional primary key enforcement: set `KEY_COLUMN` to the column name to require a non-empty value on `/append`.

## Idempotency
- Use the optional `Idempotency-Key` header on `POST /append` calls to deduplicate retries. The first write stores the JSON response in the cache and subsequent calls with the same key return that payload verbatim with an extra `Idempotency-Replayed: 1` header.
- Every `/append` reply follows `{"inserted": 1, "wrote": <bool>, "idempotency_key": <string|null>}`; when idempotency is active the cached structure is reused.
- Entries expire based on `IDEMPOTENCY_TTL_SECONDS` (default 86,400 seconds). Override the environment variable to change the retention window.
- Run the authenticated `POST /admin/idempotency/purge` maintenance endpoint to delete expired entries immediately. The endpoint responds with `{"purged": <count>}` indicating how many records were removed. All `/admin/*` routes require either a legacy bearer token or a configured API key.

### Authentication
- Bearer tokens (legacy, `Authorization: Bearer <API_TOKEN>`). The default token is `dev_token`; overriding `API_TOKEN` disables the dev token fallback unless you explicitly list `dev_token` in `API_KEYS`.
- API keys: set `API_KEYS` env var (comma-separated). Use header `X-API-Key: <key>`.

### CORS
Set `CORS_ALLOW_ORIGINS` to a comma list (`http://localhost:3000,http://example.com`).
