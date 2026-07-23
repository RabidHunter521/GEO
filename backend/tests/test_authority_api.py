"""authority API — admin-only routes (spec §8).

Local `client`/`auth_headers` fixtures (this codebase's conftest.py only
provides `db` — a real in-memory SQLite session). `client` wires that real
session into a TestClient via get_db override; `auth_headers` uses the real
ADMIN_API_KEY so test_routes_require_auth exercises real auth enforcement
rather than a bypassed dependency.
"""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.main import app
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings
    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_catalog_route_lists_items(client, db, auth_headers):
    c = _make_client(db)
    r = client.get(f"/api/v1/clients/{c.id}/authority/catalog", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(item["key"] == "gbp" for item in body)
    assert all(item["added"] is False for item in body)


def test_view_route_empty_for_new_client(client, db, auth_headers):
    c = _make_client(db)
    r = client.get(f"/api/v1/clients/{c.id}/authority", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["assets"] == []
    assert body["suggested_next"] == []
    assert body["summary"]["total"] == 0


def test_add_and_patch_and_view(client, db, auth_headers):
    c = _make_client(db)
    r = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                    json={"items": [{"asset_key": "gbp"}]})
    assert r.status_code == 200
    asset_id = r.json()[0]["id"]
    r2 = client.patch(f"/api/v1/clients/{c.id}/authority/{asset_id}", headers=auth_headers,
                      json={"status": "live", "url": "https://g.co/acme"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "live"
    view = client.get(f"/api/v1/clients/{c.id}/authority", headers=auth_headers).json()
    assert view["summary"]["live"] == 1


def test_verify_route(client, db, auth_headers):
    from app.services.url_safety import SafeResponse
    from app.services import authority_service
    c = _make_client(db)
    add = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                      json={"items": [{"asset_key": "gbp", "url": "https://g.co/acme"}]})
    asset_id = add.json()[0]["id"]
    page = "<html><body><h1>Acme Dental</h1></body></html>"
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get",
                      return_value=SafeResponse(200, page, {"content-type": "text/html"})):
        r = client.post(f"/api/v1/clients/{c.id}/authority/{asset_id}/verify", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["asset"]["status"] == "verified"
    assert isinstance(r.json()["note"], str)


def test_review_snapshot_route(client, db, auth_headers):
    c = _make_client(db)
    add = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                      json={"items": [{"asset_key": "gbp"}]})
    asset_id = add.json()[0]["id"]
    r = client.post(f"/api/v1/clients/{c.id}/authority/{asset_id}/review-snapshot",
                    headers=auth_headers, json={"rating": 4.5, "count": 58})
    assert r.status_code == 200
    assert r.json()["review_snapshots"][-1]["count"] == 58


def test_routes_require_auth(client, db):
    c = _make_client(db)
    assert client.get(f"/api/v1/clients/{c.id}/authority").status_code in (401, 403)


def test_patch_unknown_asset_404s(client, db, auth_headers):
    c = _make_client(db)
    r = client.patch(f"/api/v1/clients/{c.id}/authority/{uuid.uuid4()}",
                     headers=auth_headers, json={"status": "live"})
    assert r.status_code == 404
