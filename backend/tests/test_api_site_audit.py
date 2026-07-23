import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

_CHECKS = [
    {"id": "https", "label": "Secure connection (HTTPS)", "status": "pass",
     "detail": "The site is served over a secure connection.", "fix": ""},
]


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.archived_at = None
    return m


def _fake_audit(client_id):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.client_id = client_id
    a.checks = _CHECKS
    a.passed, a.warned, a.failed, a.unknown = 1, 0, 0, 0
    a.created_at = datetime(2026, 7, 22)
    return a


def test_run_audit_returns_persisted_row():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.site_audit.run_and_persist_site_audit",
               return_value=_fake_audit(fake_client.id)) as mock_run:
        resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/site-audit")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["passed"] == 1
    assert resp.json()["checks"][0]["id"] == "https"
    mock_run.assert_called_once()


def test_run_audit_400_when_no_website():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_client.website = None
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/site-audit")
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_latest_returns_null_when_no_audits():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.site_audit.get_latest_with_delta", return_value=None):
        resp = TestClient(app).get(f"/api/v1/clients/{fake_client.id}/site-audit/latest")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() is None


def test_latest_returns_audit_with_delta():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    payload = {"audit": _fake_audit(fake_client.id), "fixed": ["h1"], "regressed": [], "has_previous": True}
    with patch("app.api.v1.site_audit.get_latest_with_delta", return_value=payload):
        resp = TestClient(app).get(f"/api/v1/clients/{fake_client.id}/site-audit/latest")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["fixed"] == ["h1"]
    assert body["has_previous"] is True
    assert body["audit"]["passed"] == 1


def test_competitor_audit_live_only_never_persists():
    app, get_db = _make_app()
    fake_client = _fake_client()
    competitor = MagicMock()
    competitor.id = uuid.uuid4()
    competitor.client_id = fake_client.id
    competitor.name = "Rival Dental"
    competitor.website = "https://rival.com"
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, competitor]
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.site_audit.run_site_audit", return_value=_CHECKS):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/site-audit/competitor/{competitor.id}"
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Rival Dental"
    assert body["passed"] == 1
    assert "not saved" in body["note"].lower()
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


def test_competitor_audit_404_when_wrong_client():
    app, get_db = _make_app()
    fake_client = _fake_client()
    competitor = MagicMock()
    competitor.id = uuid.uuid4()
    competitor.client_id = uuid.uuid4()  # belongs to someone else
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, competitor]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/site-audit/competitor/{competitor.id}"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.parametrize("method,path", [
    ("post", "site-audit"),
    ("get", "site-audit/latest"),
    ("post", f"site-audit/competitor/{uuid.uuid4()}"),
    ("post", "toolkit/generate-llms-full"),
])
def test_new_routes_require_auth(method, path):
    from app.main import app
    resp = getattr(TestClient(app), method)(f"/api/v1/clients/{uuid.uuid4()}/{path}")
    assert resp.status_code == 401


def test_competitor_audit_400_when_no_website():
    app, get_db = _make_app()
    fake_client = _fake_client()
    competitor = MagicMock()
    competitor.id = uuid.uuid4()
    competitor.client_id = fake_client.id
    competitor.website = None
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, competitor]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/site-audit/competitor/{competitor.id}"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400
