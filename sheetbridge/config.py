from __future__ import annotations

import os
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()


class Settings(BaseModel):
    GOOGLE_SHEET_ID: str = Field(..., description="The target Google Sheet ID")
    GOOGLE_WORKSHEET: str = Field(default="Sheet1")
    CACHE_DB_PATH: str = Field(default="sheetbridge.db")
    API_TOKEN: str = Field(default="dev_token")  # simple bearer for writes
    API_KEYS: str = Field(default="", description="comma-separated API keys")
    CORS_ALLOW_ORIGINS: str = Field(default="*")
    SYNC_SECONDS: int = Field(default=60)
    GOOGLE_OAUTH_CLIENT_SECRETS: Optional[str] = Field(default=None)
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = Field(default=None)
    DELEGATED_SUBJECT: Optional[str] = Field(default=None)
    TOKEN_STORE: str = Field(default=".tokens/sheets.json")
    SYNC_ON_START: bool = Field(default=False)
    ALLOW_WRITE_BACK: bool = Field(default=False)
    SYNC_ENABLED: bool = Field(default=False)
    SYNC_INTERVAL_SECONDS: int = Field(default=300)
    SYNC_JITTER_SECONDS: int = Field(default=15)
    SYNC_BACKOFF_MAX_SECONDS: int = Field(default=600)
    IDEMPOTENCY_TTL_SECONDS: int = Field(default=86400)
    LOG_LEVEL: str = Field(default="INFO")
    RATE_LIMIT_ENABLED: bool = Field(default=False)
    RATE_LIMIT_RPS: float = Field(default=5.0)
    RATE_LIMIT_BURST: int = Field(default=20)
    SCHEMA_JSON_PATH: str = Field(default="schema.json")
    KEY_COLUMN: str | None = Field(default=None)
    UPSERT_STRICT: bool = Field(default=True)
    BULK_MAX_ITEMS: int = Field(default=500)
    SHEETS_BATCH_SIZE: int = Field(default=200)


def _load_settings(existing: Settings | None = None) -> Settings:
    values: dict[str, Any] = {}
    for name, field in Settings.model_fields.items():
        env_value = os.getenv(name)
        if env_value is None:
            if existing is not None and hasattr(existing, name):
                values[name] = getattr(existing, name)
                continue
            if field.is_required():
                continue
            values[name] = field.get_default(call_default_factory=True)
        else:
            values[name] = env_value

    try:
        return Settings(**values)
    except ValidationError as exc:
        missing = [
            str(error["loc"][0])
            for error in exc.errors()
            if error.get("type") == "missing" and error.get("loc")
        ]
        if missing:
            joined = ", ".join(sorted(set(missing)))
            raise RuntimeError(
                f"Missing required environment variables: {joined}"
            ) from exc
        raise


settings = _load_settings()


def reload_settings() -> Settings:
    global settings
    fresh = _load_settings(settings)
    settings.__dict__.update(fresh.__dict__)
    return settings
