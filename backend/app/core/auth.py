"""Admin API authentication.

Two credentials are accepted on every admin route:

1. A short-lived signed user token (HS256 JWT) minted per request by the
   Next.js server for the admin who is signed in. Claims: sub (user id),
   wid (workspace id), aud "seenby-api", iat, exp (≤ 15 min). The signing key
   is derived from ADMIN_API_KEY with a fixed label, so it is never the raw
   key itself. The user is re-loaded on every request, so deactivating an
   admin takes effect immediately, and the role comes from the database,
   never from the token.
2. The raw ADMIN_API_KEY — the "system" caller: the legacy single-admin
   login and server-to-server calls. To be removed from admin routes once
   every admin signs in with their own account (team-accounts plan, task 9).
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


async def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> None:
    # async on purpose: the identity is stored in a contextvar, and only a
    # dependency running in the request's own task can set one that the
    # (threadpool-run) endpoint then sees.
    if not credentials:
        raise _unauthorized("Missing Authorization header")
    presented = credentials.credentials
    if hmac.compare_digest(presented, settings.ADMIN_API_KEY):
        request_identity.set_current(None, None)
        return
    if presented.count(".") != 2:
        raise _unauthorized("Invalid API key")
    user = _user_from_token(presented, db)
    request_identity.set_current(user.id, user.role)


def require_owner(_: None = Depends(require_api_key)) -> None:
    """Owner-only actions. Authenticates first (FastAPI caches require_api_key
    per request, so listing both on a route does not run it twice).

    The system caller (raw key) counts as the owner: today that is the legacy
    single-admin login, which is the owner.
    """
    if not request_identity.is_owner_or_system():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can do this")
