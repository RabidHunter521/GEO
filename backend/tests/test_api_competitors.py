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
    mock_db.query.return_value.filter.return_value.all.return_value = []
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
    existing = []
    for i in range(5):
        c = MagicMock()
        c.name = f"Competitor {i}"  # distinct names so the dup check doesn't trip first
        existing.append(c)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    mock_db.query.return_value.filter.return_value.all.return_value = existing
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
    assert resp.status_code == 204


def test_delete_competitor_returns_204():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    fake_c = _fake_client()
    comp = _fake_competitor(client_id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = comp
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.delete(f"/api/v1/clients/{client_id}/competitors/{comp.id}")
    app.dependency_overrides.clear()
    assert resp.status_code == 204


def test_list_competitors_client_not_found():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_ai_readiness_returns_payload(monkeypatch):
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    fake_c = _fake_client()
    fake_c.id = client_id
    mock_db = MagicMock()
    mock_db.get.return_value = fake_c
    app.dependency_overrides[get_db] = lambda: mock_db

    from app.schemas.ai_readiness import CompetitorAIReadinessResponse, SiteAIReadiness

    payload = CompetitorAIReadinessResponse(
        client=SiteAIReadiness(
            name="Medilink", website="https://medilinkhealthcare.my",
            checked=True, has_llms_txt=False, blocked_ai_bots=[], schema_types=[],
        ),
        competitors=[],
    )
    import app.api.v1.competitors as comp_api
    monkeypatch.setattr(comp_api, "compute_competitor_ai_readiness", lambda cid, db: payload)

    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/ai-readiness")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["client"]["name"] == "Medilink"


def test_ai_readiness_client_not_found_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/ai-readiness")
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
