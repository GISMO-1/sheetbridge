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
