"""Signed per-request user tokens and the owner-only gate."""
import time
import uuid
from datetime import datetime
from unittest.mock import patch

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import request_identity
from app.core.auth import USER_TOKEN_AUDIENCE, require_api_key, require_owner, user_token_key
from app.core.constants import DEFAULT_WORKSPACE_ID
from app.core.database import get_db
from app.models.user import User

KEY = "ci-test-key"
WS = DEFAULT_WORKSPACE_ID


def _user(db, role="staff", email=None, usable=True):
    u = User(
        workspace_id=uuid.UUID(WS),
        email=email or f"{uuid.uuid4().hex[:8]}@seenby.my",
        name="U",
        role=role,
        password_hash="x" if usable else None,
        totp_secret="JBSWY3DPEHPK3PXP" if usable else None,
        totp_confirmed_at=datetime(2026, 1, 1) if usable else None,
    )
    db.add(u)
    db.commit()
    return u


def _token(user, *, wid=WS, aud=USER_TOKEN_AUDIENCE, ttl=300, key=KEY, iat=None, sub=None):
    now = int(time.time()) if iat is None else iat
    claims = {"sub": sub or str(user.id), "wid": wid, "aud": aud, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, user_token_key(key), algorithm="HS256")


@pytest.fixture
def tc(db):
    probe = FastAPI()

    @probe.get("/who", dependencies=[Depends(require_api_key)])
    def who():
        uid = request_identity.current_user_id()
        return {"user_id": str(uid) if uid else None, "role": request_identity.current_role()}

    @probe.post("/owner-only", dependencies=[Depends(require_owner)])
    def owner_only():
        return {"ok": True}

    probe.dependency_overrides[get_db] = lambda: (yield db)
    with patch("app.core.auth.settings.ADMIN_API_KEY", KEY):
        yield TestClient(probe)


def _get(tc, token):
    return tc.get("/who", headers={"Authorization": f"Bearer {token}"})


def test_raw_key_is_the_system_caller(tc):
    assert _get(tc, KEY).json() == {"user_id": None, "role": None}


def test_valid_token_identifies_the_user_with_role_from_db(db, tc):
    u = _user(db, role="staff")
    res = _get(tc, _token(u))
    assert res.status_code == 200
    assert res.json() == {"user_id": str(u.id), "role": "staff"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ttl": -120},  # expired (beyond leeway)
        {"aud": "someone-else"},
        {"key": "not-the-key"},  # signed with the wrong key
        {"wid": "b0000000-0000-4000-8000-000000000002"},  # wrong workspace
        {"ttl": 60 * 60},  # lifetime longer than allowed
        {"sub": "not-a-uuid"},
    ],
)
def test_bad_tokens_are_rejected(db, tc, kwargs):
    u = _user(db)
    assert _get(tc, _token(u, **kwargs)).status_code == 401


def test_raw_key_is_not_a_valid_signing_key(db, tc):
    u = _user(db)
    claims = {"sub": str(u.id), "wid": WS, "aud": USER_TOKEN_AUDIENCE, "iat": int(time.time()), "exp": int(time.time()) + 60}
    token = jwt.encode(claims, KEY, algorithm="HS256")
    assert _get(tc, token).status_code == 401


def test_deactivated_or_unfinished_user_is_rejected_immediately(db, tc):
    u = _user(db)
    token = _token(u)
    assert _get(tc, token).status_code == 200
    u.is_active = False
    db.commit()
    assert _get(tc, token).status_code == 401
    pending = _user(db, usable=False)
    assert _get(tc, _token(pending)).status_code == 401


def test_unknown_user_and_garbage(db, tc):
    ghost = User(id=uuid.uuid4())
    assert _get(tc, _token(ghost)).status_code == 401
    assert _get(tc, "garbage").status_code == 401
    assert tc.get("/who").status_code == 401


def test_owner_gate(db, tc):
    owner = _user(db, role="owner")
    staff = _user(db, role="staff")
    post = lambda t: tc.post("/owner-only", headers={"Authorization": f"Bearer {t}"})  # noqa: E731
    assert post(_token(owner)).status_code == 200
    assert post(_token(staff)).status_code == 403
    assert post(KEY).status_code == 200  # system caller = legacy owner login
    assert tc.post("/owner-only").status_code == 401


def test_identity_does_not_leak_between_requests(db, tc):
    u = _user(db)
    assert _get(tc, _token(u)).json()["user_id"] == str(u.id)
    assert _get(tc, KEY).json()["user_id"] is None
