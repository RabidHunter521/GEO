import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def test_health_endpoint():
    from app.main import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_scan_returns_202():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_scan = MagicMock()
    mock_scan.id = uuid.uuid4()
    mock_scan.client_id = uuid.uuid4()
    mock_scan.platform = "gemini"
    mock_scan.status = "pending"
    from datetime import datetime
    mock_scan.triggered_at = datetime(2026, 1, 1, 0, 0, 0)
    mock_scan.completed_at = None

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()

    def fake_refresh(scan_obj):
        scan_obj.id = mock_scan.id
        scan_obj.client_id = mock_scan.client_id
        scan_obj.platform = mock_scan.platform
        scan_obj.status = mock_scan.status
        scan_obj.triggered_at = mock_scan.triggered_at
        scan_obj.completed_at = mock_scan.completed_at

    mock_db.refresh = MagicMock(side_effect=fake_refresh)

    def fake_get_db():
        yield mock_db

    with patch("workers.tasks.scan_tasks.execute_scan") as mock_task:
        mock_task.delay = MagicMock()
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        client = TestClient(app)
        response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
        app.dependency_overrides.clear()

    assert response.status_code == 202


def test_trigger_scan_requires_auth():
    from app.main import app
    client = TestClient(app)
    response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_get_scan_not_found():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def fake_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[require_api_key] = lambda: None
    client = TestClient(app)
    response = client.get(f"/api/v1/scans/{uuid.uuid4()}")
    app.dependency_overrides.clear()

    assert response.status_code == 404
