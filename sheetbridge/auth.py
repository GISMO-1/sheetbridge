from fastapi import Header, HTTPException, status
from .config import settings

def require_write_token(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.API_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad token")
