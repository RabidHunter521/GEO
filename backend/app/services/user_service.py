"""Admin accounts: invites, password + mandatory 2FA, login, lockout.

An account is usable only after its invite link has been used to set a
password AND confirm an authenticator app. A password reset clears both and
issues a new link, so "reset" and "invite" are the same flow.

Tokens: the one-time link carries a random token; only its sha256 is stored.
Passwords: argon2id (argon2-cffi defaults). TOTP: RFC 6238 via pyotp, with the
last accepted time step stored so a code can't be replayed.
"""
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyotp
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy.orm import Session

from app.core.constants import (
    TOTP_DRIFT_STEPS,
    TOTP_ISSUER,
    TOTP_STEP_SECONDS,
    USER_INVITE_TTL_HOURS,
    USER_LOCKOUT_MINUTES,
    USER_MAX_FAILED_LOGINS,
    USER_PASSWORD_MAX_LENGTH,
    USER_PASSWORD_MIN_LENGTH,
    USER_ROLES,
)
from app.models.user import User

logger = structlog.get_logger()
_hasher = PasswordHasher()
# Verified against when the email is unknown, so a miss costs the same time as
# a wrong password and response timing doesn't reveal which emails exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class UserError(ValueError):
    """A user-facing validation failure (safe to show the admin)."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def check_password_policy(password: str) -> None:
    if len(password) < USER_PASSWORD_MIN_LENGTH:
        raise UserError(f"Password must be at least {USER_PASSWORD_MIN_LENGTH} characters.")
    if len(password) > USER_PASSWORD_MAX_LENGTH:
        raise UserError(f"Password must be at most {USER_PASSWORD_MAX_LENGTH} characters.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify_password(user: User | None, password: str) -> bool:
    target = user.password_hash if user is not None and user.password_hash else None
    try:
        _hasher.verify(target or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return target is not None


def _issue_link_token(user: User) -> str:
    raw = secrets.token_urlsafe(32)
    user.invite_token_hash = _token_hash(raw)
    user.invite_expires_at = _now() + timedelta(hours=USER_INVITE_TTL_HOURS)
    return raw


# ── invites / resets ─────────────────────────────────────────────────────────


def create_invite(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    email: str,
    name: str,
    role: str = "staff",
    invited_by: User | None = None,
) -> tuple[User, str]:
    """Create a not-yet-usable account and return it with its raw link token."""
    email = normalize_email(email)
    name = name.strip()
    if role not in USER_ROLES:
        raise UserError(f"Role must be one of {', '.join(USER_ROLES)}.")
    if not name:
        raise UserError("Name is required.")
    if db.query(User).filter(User.email == email).first():
        raise UserError("An account with that email already exists.")
    user = User(
        workspace_id=workspace_id,
        email=email,
        name=name,
        role=role,
        invited_by_user_id=invited_by.id if invited_by else None,
    )
    raw = _issue_link_token(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, raw


def issue_reset(db: Session, user: User) -> str:
    """Clear the password and 2FA and return a new one-time link token.

    Also used to resend an invite. The account can't sign in until the link
    is used again, which re-enrols 2FA from scratch.
    """
    user.password_hash = None
    user.totp_secret = None
    user.totp_confirmed_at = None
    user.last_totp_step = None
    user.failed_logins = 0
    user.locked_until = None
    raw = _issue_link_token(user)
    db.commit()
    return raw


def get_user_for_link(db: Session, raw_token: str) -> User | None:
    """The account a valid, unexpired link belongs to, or None."""
    if not raw_token or len(raw_token) > 128:
        return None
    user = db.query(User).filter(User.invite_token_hash == _token_hash(raw_token)).first()
    if user is None or not user.is_active:
        return None
    if user.invite_expires_at is None or user.invite_expires_at <= _now():
        return None
    return user


def begin_totp_enrolment(db: Session, user: User) -> tuple[str, str]:
    """Return (secret, otpauth URL) for the invite page.

    The secret is generated once and kept until the link is used, so reloading
    the page shows the same QR code the admin may already have scanned.
    """
    if not user.totp_secret or user.totp_confirmed_at is not None:
        user.totp_secret = pyotp.random_base32()
        user.totp_confirmed_at = None
        db.commit()
    uri = pyotp.TOTP(user.totp_secret, interval=TOTP_STEP_SECONDS).provisioning_uri(
        name=user.email, issuer_name=TOTP_ISSUER
    )
    return user.totp_secret, uri


def _match_totp_step(secret: str, code: str, now: datetime) -> int | None:
    """The time step `code` is valid for (within drift), else None."""
    code = (code or "").replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS)
    ts = now.replace(tzinfo=timezone.utc).timestamp()
    current = int(ts // TOTP_STEP_SECONDS)
    matched = None
    for step in range(current - TOTP_DRIFT_STEPS, current + TOTP_DRIFT_STEPS + 1):
        if hmac.compare_digest(totp.at(step * TOTP_STEP_SECONDS), code) and matched is None:
            matched = step
    return matched


def accept_link(db: Session, raw_token: str, password: str, code: str, now: datetime | None = None) -> User:
    """Use an invite/reset link: set the password and confirm 2FA together."""
    now = now or _now()
    user = get_user_for_link(db, raw_token)
    if user is None:
        raise UserError("This link is invalid or has expired. Ask the owner for a new one.")
    check_password_policy(password)
    if not user.totp_secret:
        raise UserError("Scan the QR code first, then enter the 6-digit code.")
    step = _match_totp_step(user.totp_secret, code, now)
    if step is None:
        raise UserError("That authenticator code is not valid. Check your phone's clock and try again.")
    user.password_hash = hash_password(password)
    user.totp_confirmed_at = now
    user.last_totp_step = step
    user.invite_token_hash = None
    user.invite_expires_at = None
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    logger.info("user_link_accepted", user_id=str(user.id))
    return user


# ── login ────────────────────────────────────────────────────────────────────


@dataclass
class LoginResult:
    user: User | None
    # "ok" | "invalid" | "locked". Callers show one generic message for both
    # failures; `reason` is for logs and tests.
    reason: str


def is_usable(user: User) -> bool:
    return bool(user.is_active and user.password_hash and user.totp_confirmed_at and user.totp_secret)


def has_usable_users(db: Session) -> bool:
    """True once at least one account can sign in. Until then the frontend
    may fall back to the legacy single-admin environment login."""
    return any(
        is_usable(u)
        for u in db.query(User).filter(User.is_active.is_(True), User.totp_confirmed_at.isnot(None))
    )


def authenticate(db: Session, email: str, password: str, code: str, now: datetime | None = None) -> LoginResult:
    now = now or _now()
    user = db.query(User).filter(User.email == normalize_email(email or "")).first()

    if user is not None and user.locked_until is not None and user.locked_until > now:
        _verify_password(None, password or "")  # same cost as a real attempt
        return LoginResult(None, "locked")

    password_ok = _verify_password(user, password or "")
    if user is None or not is_usable(user):
        return LoginResult(None, "invalid")

    step = _match_totp_step(user.totp_secret, code, now) if password_ok else None
    replayed = step is not None and user.last_totp_step is not None and step <= user.last_totp_step
    if not password_ok or step is None or replayed:
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= USER_MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=USER_LOCKOUT_MINUTES)
            user.failed_logins = 0
            logger.warning("user_locked_out", user_id=str(user.id))
        db.commit()
        return LoginResult(None, "invalid")

    user.failed_logins = 0
    user.locked_until = None
    user.last_totp_step = step
    user.last_login_at = now
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    db.commit()
    return LoginResult(user, "ok")


# ── admin actions ────────────────────────────────────────────────────────────


def set_active(db: Session, user: User, active: bool) -> None:
    user.is_active = active
    if not active:
        user.invite_token_hash = None
        user.invite_expires_at = None
    db.commit()
