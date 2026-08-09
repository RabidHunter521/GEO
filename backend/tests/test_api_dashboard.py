import uuid
from datetime import timedelta

from fastapi.testclient import TestClient as HttpClient

from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client


def _make_app(db):
    from app.main import app
    from app.core.auth import require_api_key
    from app.core.database import get_db

    app.dependency_overrides[require_api_key] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return app


def _seed(db):
    c = Client(name="Acme", website="https://acme.example", industry="retail")
    db.add(c)
    db.commit()
    db.add(ActivityLog(
        client_id=c.id, event_type="scan_failed", note="Scan failed",
        created_at=utcnow() - timedelta(days=1),
    ))
    db.commit()
    return c


def test_feed_requires_auth():
    from app.main import app
    app.dependency_overrides.clear()
    resp = HttpClient(app).get("/api/v1/dashboard/feed")
    assert resp.status_code == 401


def test_summary_requires_auth():
    from app.main import app
    app.dependency_overrides.clear()
    resp = HttpClient(app).get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_feed_returns_classified_items(db):
    c = _seed(db)
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/feed")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1 and body["has_more"] is False
    item = body["items"][0]
    assert item["client_name"] == "Acme"
    assert item["tier"] == "attention"
    assert item["link_path"] == f"/clients/{c.id}/scan"


def test_summary_shape(db):
    _seed(db)
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/summary")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["attention"]["scans_failed"] == 1
    assert set(body) == {"attention", "portfolio", "cost"}


def test_unknown_category_is_422(db):
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/feed?category=nonsense")
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_half_open_date_range_is_422(db):
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/feed?start_date=2026-08-01")
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_reversed_date_range_is_422(db):
    app = _make_app(db)
    resp = HttpClient(app).get(
        "/api/v1/dashboard/feed?start_date=2026-08-05&end_date=2026-08-01"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_client_filter_passes_through(db):
    _seed(db)
    app = _make_app(db)
    other = uuid.uuid4()
    resp = HttpClient(app).get(f"/api/v1/dashboard/feed?client_id={other}")
    app.dependency_overrides.clear()
    assert resp.status_code == 200 and resp.json()["total"] == 0
