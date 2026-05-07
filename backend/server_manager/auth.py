import hmac

from fastapi import Header, HTTPException, status

from server_manager.config import settings


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = settings.api_key
    provided = x_api_key or ""
    if not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
