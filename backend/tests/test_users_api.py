"""Team management API (owner only, workspace-scoped)."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.workspace import Workspace
from tests.test_request_identity import KEY, _token, _user


@pytest.fixture
def tc(db):
    from app.core.database import get_db

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: (yield db)
    with patch("app.core.auth.settings.ADMIN_API_KEY", KEY), patch(
        "app.api.v1.users.send_invite_email", return_value=True
    ) as sent:
        client = TestClient(app)
        client.sent = sent
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _h(user):
    return {"Authorization": f"Bearer {_token(user)}"}


def test_staff_cannot_manage_the_team(db, tc):
    staff = _user(db, role="staff")
    assert tc.get("/api/v1/users", headers=_h(staff)).status_code == 403
    assert tc.post("/api/v1/users/invite", json={"email": "x@y.z", "name": "X"}, headers=_h(staff)).status_code == 403


def test_invite_lists_and_emails(db, tc):
    owner = _user(db, role="owner", email="owner@seenby.my")
    res = tc.post("/api/v1/users/invite", json={"email": "Siti@SeenBy.my", "name": "Siti"}, headers=_h(owner))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["emailed"] is True and "/auth/invite/" in body["link"]
    assert body["user"]["status"] == "invited" and body["user"]["role"] == "staff"
    tc.sent.assert_called_once()
    listed = tc.get("/api/v1/users", headers=_h(owner)).json()
    assert {u["email"]: u["status"] for u in listed} == {"owner@seenby.my": "active", "siti@seenby.my": "invited"}
    assert all("password_hash" not in u and "totp_secret" not in u for u in listed)


def test_duplicate_invite_and_bad_role(db, tc):
    owner = _user(db, role="owner")
    tc.post("/api/v1/users/invite", json={"email": "a@seenby.my", "name": "A"}, headers=_h(owner))
    dup = tc.post("/api/v1/users/invite", json={"email": "a@seenby.my", "name": "A"}, headers=_h(owner))
    assert dup.status_code == 400 and "already exists" in dup.json()["detail"]
    bad = tc.post("/api/v1/users/invite", json={"email": "b@seenby.my", "name": "B", "role": "god"}, headers=_h(owner))
    assert bad.status_code == 400


def test_reset_issues_new_link_and_locks_out_until_used(db, tc):
    owner = _user(db, role="owner")
    staff = _user(db, role="staff")
    res = tc.post(f"/api/v1/users/{staff.id}/reset", headers=_h(owner))
    assert res.status_code == 200 and res.json()["user"]["status"] == "invited"
    db.refresh(staff)
    assert staff.password_hash is None
    # The old session's token no longer works: the account isn't usable.
    assert tc.get("/api/v1/clients", headers=_h(staff)).status_code == 401


def test_deactivate_and_reactivate(db, tc):
    owner = _user(db, role="owner")
    staff = _user(db, role="staff")
    token = _token(staff)
    assert tc.post(f"/api/v1/users/{staff.id}/deactivate", headers=_h(owner)).json()["status"] == "deactivated"
    assert tc.get("/api/v1/clients", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert tc.post(f"/api/v1/users/{staff.id}/reset", headers=_h(owner)).status_code == 409
    assert tc.post(f"/api/v1/users/{staff.id}/activate", headers=_h(owner)).json()["status"] == "active"


def test_owner_safety_rails(db, tc):
    owner = _user(db, role="owner")
    assert tc.post(f"/api/v1/users/{owner.id}/deactivate", headers=_h(owner)).status_code == 409
    # Via the system key (no caller identity): still can't remove the last owner.
    assert tc.post(
        f"/api/v1/users/{owner.id}/deactivate", headers={"Authorization": f"Bearer {KEY}"}
    ).status_code == 409
    second = _user(db, role="owner")
    assert tc.post(f"/api/v1/users/{second.id}/deactivate", headers=_h(owner)).status_code == 200


def test_other_workspaces_are_invisible(db, tc):
    owner = _user(db, role="owner")
    other_ws = Workspace(id=uuid.uuid4(), name="Other agency")
    db.add(other_ws)
    db.commit()
    stranger = User(workspace_id=other_ws.id, email="x@other.my", name="X", role="staff")
    db.add(stranger)
    db.commit()
    assert "x@other.my" not in {u["email"] for u in tc.get("/api/v1/users", headers=_h(owner)).json()}
    for action in ("reset", "deactivate", "activate"):
        assert tc.post(f"/api/v1/users/{stranger.id}/{action}", headers=_h(owner)).status_code == 404
