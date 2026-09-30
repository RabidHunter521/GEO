"""Optional expiry on the client view link: expired = the same uniform 404."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.client import Client
from app.services.share_link_service import (
    generate_share_token,
    revoke_share_token,
    share_link_is_expired,
)


def _client(db) -> Client:
    c = Client(id=uuid.uuid4(), name="Acme Dental", website="https://acme.my", industry="Dental")
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def tc(db):
    from app.core.database import get_db
    from app.core.auth import require_api_key
    from app.api.v1.client_view import _view_rate_limit

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: (yield db)
    app.dependency_overrides[_view_rate_limit] = lambda: None
    app.dependency_overrides[require_api_key] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def test_no_expiry_by_default(db):
    c = _client(db)
    generate_share_token(c, db)
    assert c.share_token_expires_at is None
    assert share_link_is_expired(c) is False


def test_expiry_is_set_from_generation_time(db):
    c = _client(db)
    generate_share_token(c, db, expires_in_days=30)
    assert c.share_token_expires_at - c.share_token_created_at == timedelta(days=30)
    assert share_link_is_expired(c) is False
    assert share_link_is_expired(c, now=c.share_token_expires_at) is True


def test_regenerate_resets_expiry_and_keeps_visit_history(db):
    c = _client(db)
    generate_share_token(c, db, expires_in_days=7)
    c.share_view_count = 3
    c.share_last_viewed_at = datetime(2026, 9, 1)
    db.commit()
    generate_share_token(c, db)  # regenerate with "never"
    assert c.share_token_expires_at is None
    assert c.share_view_count == 3


def test_revoke_clears_expiry(db):
    c = _client(db)
    generate_share_token(c, db, expires_in_days=7)
    revoke_share_token(c, db)
    assert c.share_token_expires_at is None


def test_expired_link_returns_uniform_404(db, tc):
    c = _client(db)
    generate_share_token(c, db, expires_in_days=7)
    token = c.share_token
    assert tc.post(f"/api/v1/view/{token}/visit").status_code == 204
    c.share_token_expires_at = datetime(2020, 1, 1)
    db.commit()
    expired = tc.get(f"/api/v1/view/{token}/overview")
    unknown = tc.get(f"/api/v1/view/{uuid.uuid4().hex}/overview")
    assert expired.status_code == unknown.status_code == 404
    assert expired.json() == unknown.json()


def test_generate_endpoint_accepts_expiry(db, tc):
    c = _client(db)
    res = tc.post(f"/api/v1/clients/{c.id}/share-token", json={"expires_in_days": 30})
    assert res.status_code == 200, res.text
    assert res.json()["share_token_expires_at"] is not None
    # No body keeps the old behaviour: a link that never expires.
    res = tc.post(f"/api/v1/clients/{c.id}/share-token")
    assert res.status_code == 200
    assert res.json()["share_token_expires_at"] is None


def test_generate_endpoint_rejects_unlisted_expiry(db, tc):
    c = _client(db)
    res = tc.post(f"/api/v1/clients/{c.id}/share-token", json={"expires_in_days": 3650})
    assert res.status_code == 422
