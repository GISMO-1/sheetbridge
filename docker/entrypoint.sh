#!/usr/bin/env bash
set -euo pipefail

# Default to INFO if unset
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Respect PORT if set (Railway/Heroku style)
PORT="${PORT:-8000}"

# Workers: env or sensible default = 2
WORKERS="${WORKERS:-2}"

# Bind 0.0.0.0 for containers
exec gunicorn sheetbridge.main:app \
  --workers "${WORKERS}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}" \
  --graceful-timeout 30 \
  --timeout 60 \
  --log-level "${LOG_LEVEL}"
