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
    SYNC_SECONDS: int = Field(default=60)
    GOOGLE_OAUTH_CLIENT_SECRETS: Optional[str] = Field(default=None)
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = Field(default=None)
    DELEGATED_SUBJECT: Optional[str] = Field(default=None)
    TOKEN_STORE: str = Field(default=".tokens/sheets.json")
    SYNC_ON_START: bool = Field(default=False)
    ALLOW_WRITE_BACK: bool = Field(default=False)


def _load_settings() -> Settings:
    values: dict[str, Any] = {}
    for name, field in Settings.model_fields.items():
        env_value = os.getenv(name)
        if env_value is None:
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
