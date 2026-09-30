"""Share-link open tracking: when the client last opened their view link.

A visit is an open more than SHARE_VIEW_VISIT_GAP_MINUTES after the previous
one; admin previews (X-SeenBy-Admin-Preview) are never counted.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.constants import SHARE_VIEW_VISIT_GAP_MINUTES
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.services.share_link_service import record_share_view


def _client(db) -> Client:
    c = Client(
        id=uuid.uuid4(),
        name="Acme Dental",
        website="https://acmedental.com",
        industry="Dental",
        share_token=uuid.uuid4().hex,
    )
    db.add(c)
    db.commit()
    return c


def _opened_events(db, client_id):
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.client_id == client_id, ActivityLog.event_type == "share_link_opened")
        .all()
    )


def test_first_open_counts_as_a_visit(db):
    c = _client(db)
    now = datetime(2026, 9, 30, 9, 0)
    assert record_share_view(c, db, now=now) is True
    assert c.share_view_count == 1
    assert c.share_last_viewed_at == now
    assert len(_opened_events(db, c.id)) == 1


def test_opens_within_the_gap_are_one_visit(db):
    c = _client(db)
    start = datetime(2026, 9, 30, 9, 0)
    record_share_view(c, db, now=start)
    later = start + timedelta(minutes=SHARE_VIEW_VISIT_GAP_MINUTES - 1)
    assert record_share_view(c, db, now=later) is False
    assert c.share_view_count == 1
    assert c.share_last_viewed_at == later  # last-seen still refreshes
    assert len(_opened_events(db, c.id)) == 1


def test_open_after_the_gap_is_a_new_visit(db):
    c = _client(db)
    start = datetime(2026, 9, 30, 9, 0)
    record_share_view(c, db, now=start)
    assert record_share_view(
        c, db, now=start + timedelta(minutes=SHARE_VIEW_VISIT_GAP_MINUTES + 1)
    ) is True
    assert c.share_view_count == 2
    assert len(_opened_events(db, c.id)) == 2


@pytest.fixture
def tc(db):
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: (yield db)
    app.dependency_overrides[_view_rate_limit] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def test_visit_endpoint_records_a_view(db, tc):
    c = _client(db)
    res = tc.post(f"/api/v1/view/{c.share_token}/visit")
    assert res.status_code == 204
    db.refresh(c)
    assert c.share_view_count == 1
    assert c.share_last_viewed_at is not None


def test_admin_preview_is_not_counted(db, tc):
    c = _client(db)
    res = tc.post(
        f"/api/v1/view/{c.share_token}/visit",
        headers={"X-SeenBy-Admin-Preview": "1"},
    )
    assert res.status_code == 204
    db.refresh(c)
    assert c.share_view_count == 0
    assert c.share_last_viewed_at is None


def test_visit_endpoint_uniform_404_for_bad_token(db, tc):
    res = tc.post(f"/api/v1/view/{uuid.uuid4().hex}/visit")
    assert res.status_code == 404


def test_view_fields_exposed_to_admin_not_client_view(db):
    from app.schemas.client import ClientResponse
    from app.schemas import client_view

    assert "share_last_viewed_at" in ClientResponse.model_fields
    assert "share_view_count" in ClientResponse.model_fields
    for name in dir(client_view):
        model = getattr(client_view, name)
        fields = getattr(model, "model_fields", None)
        if isinstance(fields, dict):
            assert "share_view_count" not in fields, name
            assert "share_last_viewed_at" not in fields, name


def test_view_responses_are_noindex_and_no_referrer(db, tc):
    c = _client(db)
    res = tc.get(f"/api/v1/view/{c.share_token}/overview")
    assert res.status_code == 200, res.text
    assert "noindex" in res.headers["X-Robots-Tag"]
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert "no-store" in res.headers["Cache-Control"]
