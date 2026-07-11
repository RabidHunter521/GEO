import uuid
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.schemas.provenance import ShareOfSourceResponse


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(client_id):
    m = MagicMock()
    m.id = client_id
    m.archived_at = None
    return m


def test_provenance_returns_payload(monkeypatch):
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    app.dependency_overrides[get_db] = lambda: mock_db

    payload = ShareOfSourceResponse(
        last_scan_at=None, total_third_party_sources=0, client_share=None,
        competitor_shares=[], acquisition_list=[], flip_targets=[],
    )
    import app.api.v1.competitors as comp_api
    monkeypatch.setattr(comp_api, "compute_share_of_source", lambda cid, db: payload)

    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/provenance")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["total_third_party_sources"] == 0


def test_provenance_client_not_found_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/provenance")
    app.dependency_overrides.clear()
    assert resp.status_code == 404
