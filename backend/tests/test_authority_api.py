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


def _seed_sources(db, client, domain_counts: dict[str, int]):
    """Create one completed scan whose client-owned queries cite the given
    domains the given number of times (mirrors test_authority_service.py)."""
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.scan_query_source import ScanQuerySource
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    result = ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="recommendation",
        query_text="best dental clinic KL", response_text="...", brand_detected=False,
    )
    db.add(result)
    db.commit()
    rank = 1
    for domain, n in domain_counts.items():
        for _ in range(n):
            db.add(ScanQuerySource(
                scan_query_result_id=result.id, url=f"https://{domain}/x{rank}",
                domain=domain, rank=rank, source_type="third_party", fetch_status="ok",
            ))
            rank += 1
    db.commit()
    return scan


def test_patch_response_seen_in_ai_sources_is_real_count(client, db, auth_headers):
    """PATCH must return the same non-zero seen_in_ai_sources the view route
    computes — regression for the _out(asset) default-0 bug."""
    c = _make_client(db)
    _seed_sources(db, c, {"maps.google.com": 4})  # gbp's provenance_domain is google.com
    add = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                      json={"items": [{"asset_key": "gbp"}]})
    asset_id = add.json()[0]["id"]
    r = client.patch(f"/api/v1/clients/{c.id}/authority/{asset_id}", headers=auth_headers,
                     json={"status": "live"})
    assert r.status_code == 200
    assert r.json()["seen_in_ai_sources"] == 4


def test_verify_response_last_checked_at_ends_with_z(client, db, auth_headers):
    """Mutating routes must serialize last_checked_at as UTC with a trailing
    Z, matching the view route's format — regression for the naive-datetime
    local-time-vs-UTC mismatch bug."""
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
    last_checked_at = r.json()["asset"]["last_checked_at"]
    assert last_checked_at is not None
    assert last_checked_at.endswith("Z")
