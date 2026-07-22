import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.core.time import utcnow


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(client_id, archived=False):
    m = MagicMock()
    m.id = client_id
    m.archived_at = utcnow() if archived else None
    return m


def test_get_latest_returns_null_when_none():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/content-roadmap")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() is None


def test_get_latest_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/content-roadmap")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_generate_creates_pending_row_and_dispatches_task():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    roadmap_id = uuid.uuid4()

    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)

    def fake_refresh(obj):
        obj.id = roadmap_id
        obj.client_id = client_id
        obj.status = "pending"
        obj.roadmap_json = []
        obj.source_query_count = 0
        obj.generated_at = datetime(2026, 1, 1)

    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("workers.tasks.content_tasks.run_content_roadmap") as mock_task:
        mock_task.delay = MagicMock()
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{client_id}/content-roadmap/generate")
    app.dependency_overrides.clear()

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    mock_task.delay.assert_called_once()


def test_generate_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.post(f"/api/v1/clients/{uuid.uuid4()}/content-roadmap/generate")
    assert resp.status_code == 401
