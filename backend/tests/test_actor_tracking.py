"""Who did what: actor stamped from the request's signed-in admin."""
import uuid
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.constants import WORK_LOG_CATEGORIES
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.work_log_entry import WorkLogEntry
from tests.auth_helpers import owner_headers
from tests.test_request_identity import KEY, _token, _user


@pytest.fixture
def tc(db):
    from app.core.database import get_db

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: (yield db)
    with patch("app.core.auth.settings.ADMIN_API_KEY", KEY):
        yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.my", industry="Dental")
    db.add(c)
    db.commit()
    return c


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_activity_is_stamped_with_the_signed_in_admin(db, tc):
    staff = _user(db, role="staff")
    staff.name = "Siti"
    db.commit()
    c = _client(db)
    assert tc.post(f"/api/v1/clients/{c.id}/share-token", headers=_h(_token(staff))).status_code == 200
    entry = db.query(ActivityLog).filter(ActivityLog.client_id == c.id).one()
    assert entry.actor_user_id == staff.id

    feed = tc.get(f"/api/v1/clients/{c.id}/activity", headers=_h(_token(staff))).json()
    assert feed[0]["actor_name"] == "Siti"


def test_background_work_has_no_actor(db, tc):
    c = _client(db)
    # Outside any request (Celery / scripts):
    db.add(ActivityLog(client_id=c.id, event_type="scan_completed", note="x"))
    db.commit()
    entry = db.query(ActivityLog).filter(ActivityLog.client_id == c.id).one()
    assert entry.actor_user_id is None and entry.actor_name is None
    feed = tc.get(f"/api/v1/clients/{c.id}/activity", headers=owner_headers()).json()
    assert feed[0]["actor_name"] is None


def test_publishing_work_records_who_published(db, tc):
    staff = _user(db, role="staff")
    c = _client(db)
    h = _h(_token(staff))
    created = tc.post(
        f"/api/v1/clients/{c.id}/work-log",
        json={"category": sorted(WORK_LOG_CATEGORIES)[0], "description": "Published guide", "entry_date": str(date(2026, 9, 1))},
        headers=h,
    ).json()
    # A manual entry is born published: typing it is the publish action.
    entry = db.get(WorkLogEntry, uuid.UUID(created["id"]))
    assert entry.status == "published" and entry.published_by_user_id == staff.id

    owner = _user(db, role="owner")
    tc.patch(f"/api/v1/clients/{c.id}/work-log/{created['id']}", json={"status": "suggested"}, headers=h)
    db.refresh(entry)
    assert entry.published_by_user_id is None
    tc.patch(f"/api/v1/clients/{c.id}/work-log/{created['id']}", json={"status": "published"}, headers=_h(_token(owner)))
    db.refresh(entry)
    assert entry.published_by_user_id == owner.id


def test_dashboard_feed_carries_actor(db, tc):
    staff = _user(db, role="staff")
    staff.name = "Siti"
    db.commit()
    c = _client(db)
    tc.post(f"/api/v1/clients/{c.id}/share-token", headers=_h(_token(staff)))
    items = tc.get("/api/v1/dashboard/feed?period=7d", headers=owner_headers()).json()["items"]
    assert any(i["actor_name"] == "Siti" for i in items)


def test_actor_never_reaches_the_client_view(db, tc):
    from app.schemas import client_view

    for name in dir(client_view):
        fields = getattr(getattr(client_view, name), "model_fields", None)
        if isinstance(fields, dict):
            assert not ({"actor_name", "actor_user_id", "published_by_user_id", "sent_by_user_id"} & set(fields)), name
