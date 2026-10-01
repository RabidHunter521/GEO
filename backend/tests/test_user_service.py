"""Admin accounts: invite → accept (password + 2FA) → login, lockout, reset."""
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from app.core.constants import (
    DEFAULT_WORKSPACE_ID,
    TOTP_STEP_SECONDS,
    USER_INVITE_TTL_HOURS,
    USER_LOCKOUT_MINUTES,
    USER_MAX_FAILED_LOGINS,
)
from app.services import user_service as us

WS = uuid.UUID(DEFAULT_WORKSPACE_ID)
PASSWORD = "correct horse battery"
T0 = datetime(2026, 9, 30, 9, 0, 0)


def _code(secret: str, at: datetime) -> str:
    """The code an authenticator shows at naive-UTC time `at`."""
    return pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS).at(at.replace(tzinfo=timezone.utc).timestamp())


def _active_user(db, email="staff@seenby.my", role="staff"):
    user, raw = us.create_invite(db, workspace_id=WS, email=email, name="Staff", role=role)
    secret, _ = us.begin_totp_enrolment(db, user)
    us.accept_link(db, raw, PASSWORD, _code(secret, T0), now=T0)
    return user, secret


# ── invites ──────────────────────────────────────────────────────────────────


def test_invite_creates_unusable_account_with_hashed_token(db):
    user, raw = us.create_invite(db, workspace_id=WS, email="  New@SeenBy.my ", name="New")
    assert user.email == "new@seenby.my"
    assert user.role == "staff"
    assert user.password_hash is None
    assert user.invite_token_hash and raw not in user.invite_token_hash
    assert not us.is_usable(user)
    assert us.get_user_for_link(db, raw) is user


def test_duplicate_email_rejected(db):
    us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A")
    with pytest.raises(us.UserError):
        us.create_invite(db, workspace_id=WS, email="A@SEENBY.MY", name="A2")


def test_unknown_role_rejected(db):
    with pytest.raises(us.UserError):
        us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A", role="god")


def test_expired_link_is_dead(db):
    user, raw = us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A")
    user.invite_expires_at = datetime(2020, 1, 1)
    db.commit()
    assert us.get_user_for_link(db, raw) is None
    with pytest.raises(us.UserError):
        us.accept_link(db, raw, PASSWORD, "000000")


def test_enrolment_secret_is_stable_across_reloads(db):
    user, _ = us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A")
    s1, uri = us.begin_totp_enrolment(db, user)
    s2, _ = us.begin_totp_enrolment(db, user)
    assert s1 == s2
    assert uri.startswith("otpauth://totp/SeenBy:a%40seenby.my") and "issuer=SeenBy" in uri


def test_accept_requires_valid_code_and_strong_password(db):
    user, raw = us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A")
    secret, _ = us.begin_totp_enrolment(db, user)
    with pytest.raises(us.UserError, match="at least"):
        us.accept_link(db, raw, "short", _code(secret, T0), now=T0)
    with pytest.raises(us.UserError, match="authenticator"):
        us.accept_link(db, raw, PASSWORD, "123456", now=T0)
    assert user.password_hash is None  # nothing half-applied

    us.accept_link(db, raw, PASSWORD, _code(secret, T0), now=T0)
    assert us.is_usable(user)
    assert user.invite_token_hash is None
    assert us.get_user_for_link(db, raw) is None  # one-time


# ── login ────────────────────────────────────────────────────────────────────


def test_login_success(db):
    user, secret = _active_user(db)
    later = T0 + timedelta(minutes=5)
    res = us.authenticate(db, "STAFF@seenby.my", PASSWORD, _code(secret, later), now=later)
    assert res.reason == "ok" and res.user is user
    assert user.last_login_at == later


def test_login_rejects_wrong_password_wrong_code_and_unknown_email(db):
    user, secret = _active_user(db)
    later = T0 + timedelta(minutes=5)
    good = _code(secret, later)
    assert us.authenticate(db, user.email, "wrong password!!", good, now=later).reason == "invalid"
    assert us.authenticate(db, user.email, PASSWORD, "000000", now=later).reason == "invalid"
    assert us.authenticate(db, "nobody@seenby.my", PASSWORD, good, now=later).reason == "invalid"


def test_code_cannot_be_replayed(db):
    user, secret = _active_user(db)
    later = T0 + timedelta(minutes=5)
    code = _code(secret, later)
    assert us.authenticate(db, user.email, PASSWORD, code, now=later).reason == "ok"
    assert us.authenticate(db, user.email, PASSWORD, code, now=later).reason == "invalid"


def test_the_code_used_to_enrol_cannot_be_reused_to_log_in(db):
    user, secret = _active_user(db)
    assert us.authenticate(db, user.email, PASSWORD, _code(secret, T0), now=T0).reason == "invalid"


def test_lockout_after_repeated_failures_then_expires(db):
    user, secret = _active_user(db)
    t = T0 + timedelta(minutes=5)
    for _ in range(USER_MAX_FAILED_LOGINS):
        us.authenticate(db, user.email, "wrong password!!", _code(secret, t), now=t)
    assert user.locked_until is not None
    # Even the right password + code is refused while locked.
    assert us.authenticate(db, user.email, PASSWORD, _code(secret, t), now=t).reason == "locked"
    after = t + timedelta(minutes=USER_LOCKOUT_MINUTES + 1)
    assert us.authenticate(db, user.email, PASSWORD, _code(secret, after), now=after).reason == "ok"


def test_inactive_or_unfinished_accounts_cannot_log_in(db):
    user, secret = _active_user(db)
    us.set_active(db, user, False)
    t = T0 + timedelta(minutes=5)
    assert us.authenticate(db, user.email, PASSWORD, _code(secret, t), now=t).reason == "invalid"

    pending, _ = us.create_invite(db, workspace_id=WS, email="p@seenby.my", name="P")
    assert us.authenticate(db, pending.email, PASSWORD, "000000", now=t).reason == "invalid"


def test_deactivation_kills_outstanding_link(db):
    user, raw = us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A")
    us.set_active(db, user, False)
    assert us.get_user_for_link(db, raw) is None


# ── reset ────────────────────────────────────────────────────────────────────


def test_reset_clears_password_and_2fa_and_issues_new_link(db):
    user, old_secret = _active_user(db)
    raw = us.issue_reset(db, user)
    assert user.password_hash is None and user.totp_secret is None
    assert not us.is_usable(user)
    t = T0 + timedelta(minutes=5)
    assert us.authenticate(db, user.email, PASSWORD, _code(old_secret, t), now=t).reason == "invalid"

    secret, _ = us.begin_totp_enrolment(db, user)
    assert secret != old_secret
    us.accept_link(db, raw, "a new long password", _code(secret, t), now=t)
    t2 = t + timedelta(minutes=1)
    assert us.authenticate(db, user.email, "a new long password", _code(secret, t2), now=t2).reason == "ok"


def test_invite_ttl_constant_is_applied(db):
    user, _ = us.create_invite(db, workspace_id=WS, email="a@seenby.my", name="A")
    delta = user.invite_expires_at - user.created_at
    assert abs(delta - timedelta(hours=USER_INVITE_TTL_HOURS)) < timedelta(minutes=1)
