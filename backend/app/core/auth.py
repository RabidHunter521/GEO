"""Admin API authentication.

Admin routes accept only a short-lived signed user token (HS256 JWT) minted
per request by the Next.js server for the admin who is signed in. Claims:
sub (user id), wid (workspace id), aud "seenby-api", iat, exp (≤ 15 min). The
signing key is derived from ADMIN_API_KEY with a fixed label, so it is never
the raw key itself. The user is re-loaded on every request, so deactivating
an admin takes effect immediately, and the role comes from the database,
never from the token.

The raw ADMIN_API_KEY authenticates only the service routes that run before
anyone is signed in (sign-in and invite links): require_service_key.
"""
import hashlib
import hmac
import uuid

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import request_identity
from app.core.config import settings
from app.core.database import get_db

_bearer = HTTPBearer(auto_error=False)

USER_TOKEN_AUDIENCE = "seenby-api"
USER_TOKEN_KEY_LABEL = b"seenby-user-token-v1"
USER_TOKEN_MAX_LIFETIME_SECONDS = 15 * 60


def user_token_key(api_key: str | None = None) -> bytes:
    """HMAC-SHA256(ADMIN_API_KEY, label). Mirrored in frontend src/lib/api-token.ts."""
    return hmac.new((api_key or settings.ADMIN_API_KEY).encode(), USER_TOKEN_KEY_LABEL, hashlib.sha256).digest()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _user_from_token(token: str, db: Session):
    from app.models.user import User
    from app.services.user_service import is_usable

    try:
        claims = jwt.decode(
            token,
            user_token_key(),
            algorithms=["HS256"],
            audience=USER_TOKEN_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "aud"]},
            leeway=30,
        )
        if claims["exp"] - claims["iat"] > USER_TOKEN_MAX_LIFETIME_SECONDS:
            raise jwt.InvalidTokenError("lifetime too long")
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise _unauthorized("Invalid or expired token") from exc

    user = db.get(User, user_id)
    if user is None or not is_usable(user):
        raise _unauthorized("Account is not active")
    if str(user.workspace_id) != str(claims.get("wid")):
        raise _unauthorized("Invalid token")
    return user


def require_service_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """The Next.js server itself, before any admin is signed in."""
    if not credentials or not hmac.compare_digest(credentials.credentials, settings.ADMIN_API_KEY):
        raise _unauthorized("Invalid service credential")


async def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Every admin route: a signed-in admin's user token. (Name kept from
    when this was a shared key, to avoid touching every route.)"""
    # async on purpose: the identity is stored in a contextvar, and only a
    # dependency running in the request's own task can set one that the
    # (threadpool-run) endpoint then sees.
    if not credentials:
        raise _unauthorized("Missing Authorization header")
    if credentials.credentials.count(".") != 2:
        raise _unauthorized("Invalid token")
    user = _user_from_token(credentials.credentials, db)
    request_identity.set_current(user.id, user.role, user.name)


def require_owner(_: None = Depends(require_api_key)) -> None:
    """Owner-only actions. Authenticates first (FastAPI caches require_api_key
    per request, so listing both on a route does not run it twice)."""
    if not request_identity.is_owner():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can do this")
