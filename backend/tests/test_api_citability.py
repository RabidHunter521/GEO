import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Acme"
    m.website = "https://acme.com"
    m.archived_at = None
    return m


def _fake_audit(client_id, url="https://acme.com/x", score=70):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.client_id = client_id
    a.url = url
    a.score = score
    a.checks = [{"id": "word_count", "label": "Page length", "status": "pass",
                 "detail": "ok", "points": 10}]
    a.suggestions = []
    a.suggestions_failed = False
    a.created_at = datetime(2026, 7, 23)
    return a


def test_run_page_audit_returns_row():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.citability.audit_page",
               return_value=_fake_audit(fake_client.id)) as mock_run:
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/page-audits",
            json={"url": "https://acme.com/x"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["score"] == 70
    mock_run.assert_called_once()


def test_run_page_audit_422_off_domain():
    from app.services.citability_service import OffDomainUrlError
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.citability.audit_page", side_effect=OffDomainUrlError("x")):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/page-audits",
            json={"url": "https://rival.com/x"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_run_page_audit_502_fetch_failure():
    from app.services.citability_service import PageFetchError
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.citability.audit_page", side_effect=PageFetchError("x")):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/page-audits",
            json={"url": "https://acme.com/x"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_list_returns_latest_per_url_with_previous_score(db):
    # Real db fixture: three audits over two URLs.
    from app.models.client import Client
    from app.models.page_audit import PageAudit
    from app.api.v1.citability import get_page_audit_list
    client = Client(name="Acme", website="https://acme.com",
                    industry="Dental", contact_email="a@b.co")
    db.add(client)
    db.commit()
    from datetime import datetime
    old = PageAudit(client_id=client.id, url="https://acme.com/a", score=40,
                    checks=[], created_at=datetime(2026, 7, 1))
    new = PageAudit(client_id=client.id, url="https://acme.com/a", score=75,
                    checks=[], created_at=datetime(2026, 7, 20))
    other = PageAudit(client_id=client.id, url="https://acme.com/b", score=60,
                      checks=[], created_at=datetime(2026, 7, 10))
    db.add_all([old, new, other])
    db.commit()
    items = get_page_audit_list(client.id, db)
    by_url = {i["url"]: i for i in items}
    assert by_url["https://acme.com/a"]["score"] == 75
    assert by_url["https://acme.com/a"]["previous_score"] == 40
    assert by_url["https://acme.com/b"]["previous_score"] is None


@pytest.mark.parametrize("method,path", [
    ("post", "page-audits"),
    ("get", "page-audits"),
    ("get", f"page-audits/{uuid.uuid4()}"),
])
def test_page_audit_routes_require_auth(method, path):
    from app.main import app
    resp = getattr(TestClient(app), method)(f"/api/v1/clients/{uuid.uuid4()}/{path}")
    assert resp.status_code == 401
