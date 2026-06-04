import uuid
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(client_id, archived=False):
    m = MagicMock()
    m.id = client_id
    m.archived_at = datetime.utcnow() if archived else None
    return m


def _fake_entry(event_type="scan_completed", note="Test note", day=4):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.event_type = event_type
    m.note = note
    m.created_at = datetime(2026, 6, day, 12, 0)
    return m


def test_list_activity_returns_entries_newest_first():
    """Two entries returned in the order the mock provides (newest first)."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    newer = _fake_entry("toolkit_generated", "Toolkit generated", day=4)
    older = _fake_entry("scan_completed", "Scan completed", day=3)

    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = [newer, older]

    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/activity")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["event_type"] == "toolkit_generated"
    assert data[1]["event_type"] == "scan_completed"


def test_list_activity_returns_empty_list_when_no_entries():
    app, get_db = _make_app()
    client_id = uuid.uuid4()

    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = []

    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/activity")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_activity_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/activity")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_list_activity_archived_client_returns_404():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id, archived=True)
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/activity")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_list_activity_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/activity")
    assert resp.status_code == 401
