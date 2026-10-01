"""Admin sign-in / invite-link API and the owner bootstrap script."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.core.constants import DEFAULT_WORKSPACE_ID, TOTP_STEP_SECONDS
from app.main import app
from app.models.user import User
from app.services import user_service as us

WS = uuid.UUID(DEFAULT_WORKSPACE_ID)
KEY = {"Authorization": "Bearer ci-test-key"}
PASSWORD = "correct horse battery"


def _now_code(secret: str) -> str:
    return pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS).now()


@pytest.fixture
def tc(db):
    from app.core.database import get_db

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: (yield db)
    with patch("app.core.auth.settings.ADMIN_API_KEY", "ci-test-key"):
        yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _set_up_user(db, tc, email="owner@seenby.my", role="owner"):
    user, raw = us.create_invite(db, workspace_id=WS, email=email, name="Owner", role=role)
    info = tc.get(f"/api/v1/auth/link/{raw}", headers=KEY).json()
    # The code that confirms enrolment is from the previous step, so the next
    # (current) code is still free for a login in the same test.
    prev = pyotp.TOTP(info["totp_secret"], interval=TOTP_STEP_SECONDS).at(
        datetime.now(timezone.utc).timestamp() - TOTP_STEP_SECONDS
    )
    res = tc.post(f"/api/v1/auth/link/{raw}/accept", json={"password": PASSWORD, "code": prev}, headers=KEY)
    assert res.status_code == 200, res.text
    return user, info["totp_secret"]


def test_all_auth_routes_need_the_service_credential(tc):
    assert tc.post("/api/v1/auth/login", json={"email": "a", "password": "b"}).status_code == 401
    assert tc.get("/api/v1/auth/link/x").status_code == 401


def test_no_legacy_fallback_signal(db, tc):
    # The old "no accounts yet, use the env login" answer is gone: a login
    # that doesn't match an account is simply refused.
    res = tc.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "x", "code": ""}, headers=KEY)
    assert res.status_code == 401


def test_user_tokens_cannot_call_service_routes(db, tc):
    from tests.auth_helpers import owner_headers

    assert tc.post(
        "/api/v1/auth/login", json={"email": "a@b.c", "password": "x"}, headers=owner_headers()
    ).status_code == 401


def test_link_flow_then_login(db, tc):
    user, secret = _set_up_user(db, tc)
    res = tc.post(
        "/api/v1/auth/login",
        json={"email": "Owner@SeenBy.my", "password": PASSWORD, "code": _now_code(secret)},
        headers=KEY,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {
        "id": str(user.id),
        "email": "owner@seenby.my",
        "name": "Owner",
        "role": "owner",
        "workspace_id": DEFAULT_WORKSPACE_ID,
    }


def test_login_failures_are_indistinguishable(db, tc):
    _, secret = _set_up_user(db, tc)
    bad = [
        {"email": "owner@seenby.my", "password": "wrong password!!", "code": _now_code(secret)},
        {"email": "owner@seenby.my", "password": PASSWORD, "code": "000000"},
        {"email": "nobody@seenby.my", "password": PASSWORD, "code": _now_code(secret)},
    ]
    answers = {tc.post("/api/v1/auth/login", json=b, headers=KEY).text for b in bad}
    assert len(answers) == 1


def test_link_info_and_accept_errors(db, tc):
    assert tc.get("/api/v1/auth/link/not-a-real-token", headers=KEY).status_code == 404
    user, raw = us.create_invite(db, workspace_id=WS, email="s@seenby.my", name="S")
    info = tc.get(f"/api/v1/auth/link/{raw}", headers=KEY).json()
    assert info["email"] == "s@seenby.my" and info["is_reset"] is False
    assert info["otpauth_uri"].startswith("otpauth://totp/")
    res = tc.post(f"/api/v1/auth/link/{raw}/accept", json={"password": "short", "code": "1"}, headers=KEY)
    assert res.status_code == 400 and "at least" in res.json()["detail"]
    # The response never carries secrets.
    ok = tc.post(
        f"/api/v1/auth/link/{raw}/accept",
        json={"password": PASSWORD, "code": _now_code(info["totp_secret"])},
        headers=KEY,
    ).json()
    assert "password_hash" not in ok and "totp_secret" not in ok


def test_invite_email_contains_one_time_link_and_company_line(db):
    from app.core.constants import COMPANY_IDENTITY_LINE
    from app.services.user_invite_email import build_invite_email

    user, raw = us.create_invite(db, workspace_id=WS, email="s@seenby.my", name="Siti")
    subject, body = build_invite_email(user, raw, is_reset=False, invited_by="Faris")
    assert "invited" in subject
    assert f"/auth/invite/{raw}" in body
    assert "Faris has invited you" in body and "Hi Siti" in body
    assert COMPANY_IDENTITY_LINE.replace("&", "&amp;") in body


def test_create_owner_script(db, capsys):
    from scripts import create_owner

    class _NoClose:
        def __init__(self, s):
            self._s = s

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    with patch.object(create_owner, "SessionLocal", lambda: _NoClose(db)), patch.object(
        create_owner, "send_invite_email", return_value=False
    ):
        assert create_owner.main(["Faris@SeenBy.my", "Faris"]) == 0
        out = capsys.readouterr().out
        assert "/auth/invite/" in out and "could not be sent" in out
        owner = db.query(User).filter(User.email == "faris@seenby.my").one()
        assert owner.role == "owner" and owner.workspace_id == WS

        # Running again before setup re-issues a link; the old one dies.
        old_hash = owner.invite_token_hash
        assert create_owner.main(["faris@seenby.my", "Faris"]) == 0
        assert owner.invite_token_hash != old_hash

        # Once set up, it refuses.
        secret, _ = us.begin_totp_enrolment(db, owner)
        raw = capsys.readouterr().out.split("/auth/invite/")[1].split()[0]
        us.accept_link(db, raw, PASSWORD, _now_code(secret))
        assert create_owner.main(["faris@seenby.my", "Faris"]) == 1
