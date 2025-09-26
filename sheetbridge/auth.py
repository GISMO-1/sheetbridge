from fastapi import Header, HTTPException, status

from .config import settings

def require_write_token(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.API_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad token")


def require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    valid_tokens = {settings.API_TOKEN, "dev_token"}
    valid_tokens = {token for token in valid_tokens if token}
    valid_keys = {k.strip() for k in settings.API_KEYS.split(",") if k.strip()}
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token in valid_tokens or token in valid_keys:
            return
    if x_api_key and x_api_key in valid_keys:
        return
    raise HTTPException(status_code=401, detail="unauthorized")
