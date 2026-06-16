import base64
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
    m.country = None
    m.contact_email = None
    m.logo_url = None
    m.brand_authority_score = 0
    m.brand_authority_evidence = None
    m.content_quality_score = 0
    m.content_quality_evidence = None
    m.technical_foundations_verified = False
    m.structured_data_verified = False
    m.score_drop_threshold = 35
    m.scan_cadence_days = 30
    m.share_token = None
    m.share_token_created_at = None
    m.created_at = datetime(2026, 1, 1)
    m.archived_at = None
    m.is_prospect = False
    m.internal_notes = None
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


def test_list_clients_serializes_enrichment_fields():
    from unittest.mock import patch
    from datetime import datetime
    from app.schemas.client import ClientListItem, ClientResponse

    fake = _fake_client("Acme Corp")
    fake.enabled_platforms = ["chatgpt"]
    base = ClientResponse.model_validate(fake, from_attributes=True).model_dump()
    item = ClientListItem(
        **base,
        latest_overall_score=70.0,
        last_scan_at=datetime(2026, 6, 10),
        previous_overall_score=62.5,
        latest_scan_status="completed",
        latest_scan_triggered_at=datetime(2026, 6, 10),
    )

    app, get_db = _make_app()
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.clients.build_client_list", return_value=[item]):
        client = TestClient(app)
        response = client.get("/api/v1/clients")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()[0]
    assert body["latest_overall_score"] == 70.0
    assert body["previous_overall_score"] == 62.5
    assert body["latest_scan_status"] == "completed"
    assert body["latest_scan_triggered_at"] is not None


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
        obj.scan_cadence_days = 30
        obj.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]
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

    def fake_refresh(obj):
        obj.city = "Kuala Lumpur"

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"city": "Kuala Lumpur"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["city"] == "Kuala Lumpur"


def _logo_ready_client(name="Logo Co"):
    existing = _fake_client(name)
    existing.enabled_platforms = ["chatgpt"]
    existing.is_prospect = False
    return existing


def test_upload_logo_rejects_unsupported_type():
    app, get_db = _make_app()
    existing = _logo_ready_client()
    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.post(
        f"/api/v1/clients/{existing.id}/logo",
        files={"file": ("logo.txt", b"not an image", "text/plain")},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 400


# A real 1x1 PNG — the upload path now sniffs the actual bytes, so a fake
# header no longer passes.
_VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_upload_logo_success_sets_url():
    from unittest.mock import patch
    app, get_db = _make_app()
    existing = _logo_ready_client()
    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    with patch(
        "app.api.v1.clients.r2_service.upload_image",
        return_value="https://cdn.example/logos/abc.png",
    ) as mock_upload:
        response = client.post(
            f"/api/v1/clients/{existing.id}/logo",
            files={"file": ("logo.png", _VALID_PNG, "image/png")},
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["logo_url"] == "https://cdn.example/logos/abc.png"
    assert mock_upload.called


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


def test_update_internal_notes():
    """PATCH internal_notes is accepted and echoed in the response."""
    app, get_db = _make_app()
    existing = _fake_client("Notes Co")
    # internal_notes and is_prospect must exist on the mock for ClientResponse validation
    existing.is_prospect = False
    existing.internal_notes = None
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    # refresh is a no-op, so the field can only appear in the response if the
    # route's setattr loop actually applied it — i.e. internal_notes is a real
    # ClientUpdate field. If it were dropped from the schema, this would fail.
    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"internal_notes": "Follow up after July demo"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["internal_notes"] == "Follow up after July demo"
    assert existing.internal_notes == "Follow up after July demo"


@pytest.mark.parametrize("method,path", [
    ("GET",   "/api/v1/clients"),
    ("POST",  "/api/v1/clients"),
    ("GET",   f"/api/v1/clients/{uuid.uuid4()}"),
    ("PATCH", f"/api/v1/clients/{uuid.uuid4()}"),
    ("GET",   f"/api/v1/clients/{uuid.uuid4()}/geo-score/latest"),
])
def test_endpoints_require_auth(method, path):
    from app.main import app
    client = TestClient(app)
    response = client.request(method, path, json={})
    assert response.status_code == 401
