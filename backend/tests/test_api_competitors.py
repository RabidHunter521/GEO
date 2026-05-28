import uuid
import pytest
from unittest.mock import MagicMock
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
    m.archived_at = None
    return m


def _fake_competitor(client_id):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.client_id = client_id
    m.name = "Rival Co"
    m.website = "https://rival.com"
    return m


def test_list_competitors_empty():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    fake_c = _fake_client()
    fake_c.id = client_id
    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    mock_db.query.return_value.filter.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_competitor_returns_201():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    fake_c = _fake_client()
    fake_c.id = client_id
    comp = _fake_competitor(client_id)

    def fake_refresh(obj):
        obj.id = comp.id
        obj.client_id = comp.client_id
        obj.name = comp.name
        obj.website = comp.website

    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    mock_db.query.return_value.filter.return_value.count.return_value = 0
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.post(
        f"/api/v1/clients/{client_id}/competitors",
        json={"name": "Rival Co", "website": "https://rival.com"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 201
    assert resp.json()["name"] == "Rival Co"


def test_add_competitor_rejects_over_limit():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    fake_c = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    mock_db.query.return_value.filter.return_value.count.return_value = 5
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.post(
        f"/api/v1/clients/{client_id}/competitors",
        json={"name": "Extra Co"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_delete_competitor_not_found():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    fake_c = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.delete(f"/api/v1/clients/{client_id}/competitors/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_list_competitors_client_not_found():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.parametrize("method,path_suffix", [
    ("GET",    "/competitors"),
    ("POST",   "/competitors"),
    ("DELETE", f"/competitors/{uuid.uuid4()}"),
])
def test_competitor_endpoints_require_auth(method, path_suffix):
    from app.main import app
    client_id = uuid.uuid4()
    http = TestClient(app)
    resp = http.request(method, f"/api/v1/clients/{client_id}{path_suffix}", json={})
    assert resp.status_code == 401
