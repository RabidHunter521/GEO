import uuid
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(name="Acme Corp"):
    from datetime import datetime
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = name
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = None
    m.target_audience = None
    m.city = None
    m.state = None
    m.contact_email = None
    m.brand_authority_score = 0
    m.content_quality_score = 0
    m.technical_foundations_verified = False
    m.structured_data_verified = False
    m.score_drop_threshold = 35
    m.created_at = datetime(2026, 1, 1)
    m.archived_at = None
    return m


def test_list_clients_returns_empty():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get("/api/v1/clients")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == []


def test_create_client_returns_201():
    app, get_db = _make_app()
    created = _fake_client("TestCo")

    def fake_refresh(obj):
        obj.id = created.id
        obj.name = created.name
        obj.website = created.website
        obj.industry = created.industry
        obj.description = None
        obj.target_audience = None
        obj.city = None
        obj.state = None
        obj.contact_email = None
        obj.brand_authority_score = 0
        obj.content_quality_score = 0
        obj.technical_foundations_verified = False
        obj.structured_data_verified = False
        obj.score_drop_threshold = 35
        from datetime import datetime
        obj.created_at = datetime(2026, 1, 1)
        obj.archived_at = None

    mock_db = MagicMock()
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.post(
        "/api/v1/clients",
        json={"name": "TestCo", "website": "https://test.co", "industry": "SaaS"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json()["name"] == "TestCo"


def test_get_client_not_found():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get(f"/api/v1/clients/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_update_client():
    app, get_db = _make_app()
    existing = _fake_client("Old Name")
    existing.city = None

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"city": "Kuala Lumpur"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200


def test_latest_geo_score_returns_none_when_no_scans():
    app, get_db = _make_app()
    existing = _fake_client()

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get(f"/api/v1/clients/{existing.id}/geo-score/latest")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() is None


def test_endpoints_require_auth():
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/v1/clients")
    assert response.status_code == 401
