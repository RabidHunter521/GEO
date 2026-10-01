"""Admin sign-in and invite links.

Called by the Next.js server, never by a browser: every route requires the
service credential (require_api_key). The invite page is server-rendered by
Next, which is why even the link routes go through here.
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.schemas.user import LinkAcceptRequest, LinkInfo, LoginRequest, UserPublic
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_api_key)])

_INVALID = "Invalid email, password or authenticator code"


@router.post("/login", response_model=UserPublic)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # Until the first account is fully set up, tell the frontend so it can use
    # the legacy single-admin login instead. After that, the legacy login is off.
    if not user_service.has_usable_users(db):
        raise HTTPException(status_code=409, detail="no_users")
    result = user_service.authenticate(db, body.email, body.password, body.code)
    if result.user is None:
        # Same answer for wrong password, wrong code, unknown email and a
        # locked account: nothing here tells an attacker which one it was.
        raise HTTPException(status_code=401, detail=_INVALID)
    return result.user


def _link_user(db: Session, token: str):
    user = user_service.get_user_for_link(db, token)
    if user is None:
        raise HTTPException(status_code=404, detail="This link is invalid or has expired.")
    return user


@router.get("/link/{token}", response_model=LinkInfo)
def inspect_link(token: str = Path(max_length=128), db: Session = Depends(get_db)):
    user = _link_user(db, token)
    secret, uri = user_service.begin_totp_enrolment(db, user)
    return LinkInfo(
        email=user.email,
        name=user.name,
        is_reset=user.last_login_at is not None,  # has signed in before
        totp_secret=secret,
        otpauth_uri=uri,
    )


@router.post("/link/{token}/accept", response_model=UserPublic)
def accept_link(body: LinkAcceptRequest, token: str = Path(max_length=128), db: Session = Depends(get_db)):
    try:
        return user_service.accept_link(db, token, body.password, body.code)
    except user_service.UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
