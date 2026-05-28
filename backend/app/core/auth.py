from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def require_api_key(authorization: str | None = Security(_api_key_header)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
