from fastapi import Header, HTTPException, status

from .config import settings

def require_write_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    valid_token = (settings.API_TOKEN or "").strip()
    valid_keys = {k.strip() for k in settings.API_KEYS.split(",") if k.strip()}

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token == valid_token or token in valid_keys:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad token")

    if x_api_key and x_api_key in valid_keys:
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")


def require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    configured_token = (settings.API_TOKEN or "").strip()
    valid_tokens = {configured_token} if configured_token else set()
    valid_keys = {k.strip() for k in settings.API_KEYS.split(",") if k.strip()}
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token in valid_tokens or token in valid_keys:
            return
    if x_api_key and x_api_key in valid_keys:
        return
    raise HTTPException(status_code=401, detail="unauthorized")
