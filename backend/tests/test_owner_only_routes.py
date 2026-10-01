"""Owner-only actions: staff get 403, the owner (and legacy system key) pass."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.client import Client
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


def _client(db, *, prospect=False):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.my", industry="Dental", is_prospect=prospect)
    db.add(c)
    db.commit()
    return c


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_staff_cannot_archive_a_client_but_owner_can(db, tc):
    staff, owner = _user(db, role="staff"), _user(db, role="owner")
    c = _client(db)
    res = tc.delete(f"/api/v1/clients/{c.id}", headers=_auth(_token(staff)))
    assert res.status_code == 403
    db.refresh(c)
    assert c.archived_at is None
    assert tc.delete(f"/api/v1/clients/{c.id}", headers=_auth(_token(owner))).status_code == 204


def test_staff_can_clear_out_prospects(db, tc):
    staff = _user(db, role="staff")
    p = _client(db, prospect=True)
    assert tc.delete(f"/api/v1/clients/{p.id}", headers=_auth(_token(staff))).status_code == 204


def test_legacy_system_key_still_archives(db, tc):
    c = _client(db)
    assert tc.delete(f"/api/v1/clients/{c.id}", headers=_auth(KEY)).status_code == 204


def test_benchmark_publishing_is_owner_only(db, tc):
    staff = _user(db, role="staff")
    body = {
        "slug": "kl-dental-2026-q3",
        "title": "KL dental",
        "edition": "2026-Q3",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "generated_by": "x",
        "methodology_version": "v1",
    }
    fake = str(uuid.uuid4())
    staff_h = _auth(_token(staff))
    assert tc.post("/api/v1/benchmarks/publications", json=body, headers=staff_h).status_code == 403
    assert tc.post(f"/api/v1/benchmarks/publications/{fake}/approve", json={"approved_by": "x"}, headers=staff_h).status_code == 403
    assert tc.post(f"/api/v1/benchmarks/publications/{fake}/publish", headers=staff_h).status_code == 403
    assert tc.post(f"/api/v1/benchmarks/publications/{fake}/withdraw", json={"reason": "x"}, headers=staff_h).status_code == 403
    # Reading the list stays open to staff.
    assert tc.get("/api/v1/benchmarks/publications", headers=staff_h).status_code == 200


def test_staff_can_still_do_everyday_work(db, tc):
    staff = _user(db, role="staff")
    c = _client(db)
    h = _auth(_token(staff))
    assert tc.get("/api/v1/clients", headers=h).status_code == 200
    assert tc.patch(f"/api/v1/clients/{c.id}", json={"city": "Kuala Lumpur"}, headers=h).status_code == 200
