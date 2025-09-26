# HANDOFF
Status: MVP API up with /health, /rows (read), /rows (write with bearer). Sheets OAuth not wired yet.

Next:
1) Add Google OAuth device flow and service account option.
2) Implement periodic sync Sheet → SQLite.
3) Implement append write-back.

Env:
- Python 3.11
- FastAPI, SQLModel, google-api-python-client
