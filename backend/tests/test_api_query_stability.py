"""API contract for the query-stability endpoints (Phase 5 Task 8).

- Admin endpoint ``GET /clients/{client_id}/query-stability`` — authenticated,
  returns ``list[QueryStabilityResponse]``.
- Client-view endpoint ``GET /view/{token}/query-stability`` — token-gated,
  non-prospect only, returns the same shape (stability data carries no
  admin-only fields per CLAUDE.md §8).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _make_client(db, *, is_prospect=False, name="Acme Dental"):
    from app.models.client import Client

    c = Client(
        id=uuid.uuid4(),
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
        share_token=uuid.uuid4().hex,
        scan_cadence_days=30,
        is_prospect=is_prospect,
    )
    db.add(c)
    db.flush()
    db.commit()
    return c


@pytest.fixture
def admin_client(db):
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings

    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


# ── Admin endpoint ──────────────────────────────────────────────────────────


def test_admin_requires_auth(admin_client, db):
    c = _make_client(db)
    r = admin_client.get(f"/api/v1/clients/{c.id}/query-stability")
    assert r.status_code == 401


def test_admin_404_for_nonexistent_client(admin_client, auth_headers):
    r = admin_client.get(
        f"/api/v1/clients/{uuid.uuid4()}/query-stability", headers=auth_headers
    )
    assert r.status_code == 404


def test_admin_404_for_archived_client(admin_client, db, auth_headers):
    from app.core.time import utcnow

    c = _make_client(db)
    c.archived_at = utcnow()
    db.commit()
    r = admin_client.get(
        f"/api/v1/clients/{c.id}/query-stability", headers=auth_headers
    )
    assert r.status_code == 404


def test_admin_returns_empty_for_new_client(admin_client, db, auth_headers):
    c = _make_client(db)
    r = admin_client.get(
        f"/api/v1/clients/{c.id}/query-stability", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json() == []


# ── Client-view endpoint ───────────────────────────────────────────────────


def test_view_404_for_invalid_token(admin_client):
    r = admin_client.get("/api/v1/view/invalidtoken/query-stability")
    assert r.status_code == 404


def test_view_404_for_prospect(admin_client, db):
    c = _make_client(db, is_prospect=True)
    r = admin_client.get(f"/api/v1/view/{c.share_token}/query-stability")
    assert r.status_code == 404


def test_view_returns_empty_for_new_client(admin_client, db):
    c = _make_client(db)
    r = admin_client.get(f"/api/v1/view/{c.share_token}/query-stability")
    assert r.status_code == 200
    assert r.json() == []
