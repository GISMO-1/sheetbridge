from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    GOOGLE_SHEET_ID: str = Field(..., description="The target Google Sheet ID")
    GOOGLE_WORKSHEET: str = Field(default="Sheet1")
    CACHE_DB_PATH: str = Field(default="sheetbridge.db")
    API_TOKEN: str = Field(default="dev_token")  # simple bearer for writes
    SYNC_SECONDS: int = Field(default=60)

    class Config:
        env_file = ".env"

settings = Settings()
