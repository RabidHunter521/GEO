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


def _fake_deliverable(client_id, status="draft"):
    d = MagicMock()
    d.id = uuid.uuid4()
    d.client_id = client_id
    d.type = "faq_pack"
    d.competitor_id = None
    d.title = "FAQ pack"
    d.body_md = "# FAQ"
    d.status = status
    d.generated_at = datetime(2026, 7, 23)
    d.reviewed_at = None
    return d


def test_generate_deliverable_returns_draft():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.deliverables.generate_deliverable",
               return_value=_fake_deliverable(fake_client.id)):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "faq_pack"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


def test_generate_unknown_type_422():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "poem"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_comparison_requires_competitor_id():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "comparison_page"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_generate_claude_failure_502():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.deliverables.generate_deliverable", return_value=None):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "glossary"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_patch_marks_reviewed_and_logs():
    app, get_db = _make_app()
    fake_client = _fake_client()
    d = _fake_deliverable(fake_client.id, status="draft")
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, d]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).patch(
        f"/api/v1/clients/{fake_client.id}/deliverables/{d.id}",
        json={"status": "reviewed"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert d.status == "reviewed"
    assert d.reviewed_at is not None
    assert mock_db.add.called  # ActivityLog deliverable_reviewed
    assert mock_db.commit.called


def test_patch_reviewed_back_to_draft_rejected():
    app, get_db = _make_app()
    fake_client = _fake_client()
    d = _fake_deliverable(fake_client.id, status="reviewed")
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, d]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).patch(
        f"/api/v1/clients/{fake_client.id}/deliverables/{d.id}",
        json={"status": "draft"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_download_returns_markdown_attachment():
    app, get_db = _make_app()
    fake_client = _fake_client()
    d = _fake_deliverable(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, d]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).get(
        f"/api/v1/clients/{fake_client.id}/deliverables/{d.id}/download"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.text == "# FAQ"


@pytest.mark.parametrize("method,path", [
    ("post", "deliverables"),
    ("get", "deliverables"),
    ("patch", f"deliverables/{uuid.uuid4()}"),
    ("get", f"deliverables/{uuid.uuid4()}/download"),
])
def test_deliverable_routes_require_auth(method, path):
    from app.main import app
    resp = getattr(TestClient(app), method)(f"/api/v1/clients/{uuid.uuid4()}/{path}")
    assert resp.status_code == 401
