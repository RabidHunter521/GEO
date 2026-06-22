import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.core.auth import require_api_key


def _setup_overrides(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_api_key] = lambda: None


def _make_client_id():
    return uuid.uuid4()


def _mock_db_with_client(client_id):
    """Return a mock DB where db.get(Client, id) returns a live client."""
    mock_client = MagicMock()
    mock_client.id = client_id
    mock_client.archived_at = None
    mock_client.brand_authority_score = 0
    mock_db = MagicMock()
    mock_db.get.return_value = mock_client
    return mock_db, mock_client


def _fake_assessment(client_id, dimension="brand_authority", suggested_score=58, final_score=None, status="suggested"):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.client_id = client_id
    row.dimension = dimension
    row.suggested_score = suggested_score
    row.final_score = final_score
    row.status = status
    row.evidence_bullets = ["Listed on Google with 40 reviews"]
    row.raw_narrative = "ok"
    row.generated_at = datetime(2026, 1, 1, 0, 0, 0)
    row.reviewed_at = None
    return row


def test_generate_endpoint_returns_draft():
    client_id = _make_client_id()
    mock_db, _ = _mock_db_with_client(client_id)
    _setup_overrides(mock_db)

    fake_row = _fake_assessment(client_id)
    with patch("app.services.assessment_service.generate_assessment", return_value=fake_row):
        r = TestClient(app).post(f"/api/v1/clients/{client_id}/assessments/brand_authority/generate")

    assert r.status_code == 200
    body = r.json()
    assert body["suggested_score"] == 58
    assert body["status"] == "suggested"
    assert body["final_score"] is None
    app.dependency_overrides.clear()


def test_generate_unknown_dimension_422():
    client_id = _make_client_id()
    mock_db, _ = _mock_db_with_client(client_id)
    _setup_overrides(mock_db)

    r = TestClient(app).post(f"/api/v1/clients/{client_id}/assessments/nope/generate")
    assert r.status_code == 422
    app.dependency_overrides.clear()


def test_generate_failure_returns_502():
    client_id = _make_client_id()
    mock_db, _ = _mock_db_with_client(client_id)
    _setup_overrides(mock_db)

    with patch("app.services.assessment_service.generate_assessment", return_value=None):
        r = TestClient(app).post(f"/api/v1/clients/{client_id}/assessments/brand_authority/generate")

    assert r.status_code == 502
    app.dependency_overrides.clear()


def test_accept_endpoint_writes_score():
    client_id = _make_client_id()
    mock_db, mock_client = _mock_db_with_client(client_id)
    _setup_overrides(mock_db)

    accepted_row = _fake_assessment(client_id, final_score=65, status="adjusted")

    with patch("app.services.assessment_service.accept_assessment", return_value=accepted_row):
        r = TestClient(app).post(
            f"/api/v1/clients/{client_id}/assessments/brand_authority/accept",
            json={"final_score": 65},
        )

    assert r.status_code == 200
    assert r.json()["final_score"] == 65
    app.dependency_overrides.clear()
