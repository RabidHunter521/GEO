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
    m.phone = None
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
    m.avg_deal_value_rm = None
    m.visitor_to_lead_pct = 2
    m.lead_to_customer_pct = 20
    m.share_token = None
    m.share_token_created_at = None
    m.ga4_property_id = None
    m.created_at = datetime(2026, 1, 1)
    m.archived_at = None
    m.is_prospect = False
    m.internal_notes = None
    m.industry_pack = None
    m.industry_subcategory = None
    m.industry_pack_version = None
    m.benchmark_opt_out = False
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
        obj.avg_deal_value_rm = None
        obj.visitor_to_lead_pct = 2
        obj.lead_to_customer_pct = 20
        obj.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]
        from datetime import datetime
        obj.created_at = datetime(2026, 1, 1)
        obj.archived_at = None
        obj.benchmark_opt_out = False

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


def test_update_client_persists_phone():
    """phone must survive PATCH request parsing and GET response serialization
    end to end — the schema previously dropped it, silently defeating the
    NAP-mismatch check in authority_service (nap_mismatch always saw None)."""
    app, get_db = _make_app()
    existing = _fake_client("Phone Co")
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    # refresh is a no-op: the route's setattr loop mutates `existing` directly,
    # so `existing` doubles as the "persisted row" for this MagicMock-backed test.
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    patch_response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"phone": "+60 12-345 6789"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["phone"] == "+60 12-345 6789"
    # Proves the route's setattr actually applied phone to the row (request
    # parsing side) rather than Pydantic silently dropping the unknown field.
    assert existing.phone == "+60 12-345 6789"

    get_response = client.get(f"/api/v1/clients/{existing.id}")
    app.dependency_overrides.clear()
    assert get_response.status_code == 200
    # Proves ClientResponse no longer strips phone on read.
    assert get_response.json()["phone"] == "+60 12-345 6789"


def test_update_client_persists_industry_pack():
    """Same end-to-end guarantee `phone` needed: PATCH parsing must apply the
    field to the row, and the response schema must not strip it on read."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    patch_response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "healthcare", "industry_subcategory": "dental"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["industry_pack"] == "healthcare"
    assert patch_response.json()["industry_subcategory"] == "dental"
    # Proves the route's setattr loop applied them to the row rather than
    # Pydantic silently dropping unknown fields.
    assert existing.industry_pack == "healthcare"
    assert existing.industry_subcategory == "dental"

    get_response = client.get(f"/api/v1/clients/{existing.id}")
    app.dependency_overrides.clear()
    assert get_response.status_code == 200
    assert get_response.json()["industry_pack"] == "healthcare"


def test_update_client_persists_benchmark_opt_out():
    """Same end-to-end guarantee `phone` needed: PATCH parsing must apply the
    field to the row, and the response schema must not strip it on read."""
    app, get_db = _make_app()
    existing = _fake_client("Opt Out Co")
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    patch_response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"benchmark_opt_out": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["benchmark_opt_out"] is True
    # Proves the route's setattr loop applied it to the row rather than
    # Pydantic silently dropping an unknown field.
    assert existing.benchmark_opt_out is True

    get_response = client.get(f"/api/v1/clients/{existing.id}")
    assert get_response.status_code == 200
    assert get_response.json()["benchmark_opt_out"] is True

    # And it toggles back — this is not a one-way switch like industry_pack.
    revert_response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"benchmark_opt_out": False},
    )
    app.dependency_overrides.clear()
    assert revert_response.status_code == 200
    assert revert_response.json()["benchmark_opt_out"] is False
    assert existing.benchmark_opt_out is False


def test_update_client_defaults_benchmark_opt_out_to_false():
    """A client created before this field existed must read as participating
    by default, not as opted out — absence of a value is not the same as an
    explicit opt-out."""
    app, get_db = _make_app()
    existing = _fake_client("Default Co")
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.get(f"/api/v1/clients/{existing.id}")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["benchmark_opt_out"] is False


def test_update_client_never_writes_the_confirmation_control_field():
    """`confirm_pack_change` gates the mutation; the route blind-setattrs every
    parsed field, so it must be popped before that loop."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "fnb", "confirm_pack_change": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    # MagicMock would happily accept the attribute, so assert it was never set.
    assert "confirm_pack_change" not in existing.__dict__
    assert "confirm_pack_change" not in response.json()


def test_update_client_rejects_unknown_industry_pack():
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "retail"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 422
    assert existing.industry_pack is None


def test_setting_industry_pack_the_first_time_needs_no_confirmation():
    """None -> healthcare is a first selection, not a change; nothing is invalidated."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = None
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "healthcare"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.industry_pack == "healthcare"


def test_changing_an_existing_industry_pack_requires_confirmation():
    """Switching packs invalidates generated queries and benchmark comparability,
    so an unconfirmed change must return the impact preview and persist nothing."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = "healthcare"
    existing.industry_subcategory = "dental"
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "fnb"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["current_pack"] == "healthcare"
    assert detail["requested_pack"] == "fnb"
    assert detail["requires_confirmation"] is True
    # Nothing may be written, and nothing may be committed, on a refused change.
    assert existing.industry_pack == "healthcare"
    assert existing.industry_subcategory == "dental"
    mock_db.commit.assert_not_called()


def test_confirmed_industry_pack_change_persists():
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = "healthcare"
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "fnb", "confirm_pack_change": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.industry_pack == "fnb"


def test_pack_change_clears_the_stale_subcategory_and_restamps_the_version():
    """Subcategories are pack-specific — "dental" is meaningless under F&B — and
    the version records which pack's rules produced the stored evidence. Leaving
    either behind describes a pack the client no longer has.

    The version is RE-STAMPED from the new pack's registry entry rather than
    cleared: this test asserted None while no packs were registered, which
    silently became wrong the moment the F&B pack landed."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = "healthcare"
    existing.industry_subcategory = "dental"
    existing.industry_pack_version = "1.0.0"
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "fnb", "confirm_pack_change": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.industry_pack == "fnb"
    assert existing.industry_subcategory is None
    from app.industry_packs import registry

    assert existing.industry_pack_version == registry.get_pack("fnb").version


def test_pack_change_keeps_a_subcategory_sent_in_the_same_request():
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = "healthcare"
    existing.industry_subcategory = "dental"
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={
            "industry_pack": "fnb",
            "industry_subcategory": "cafe",
            "confirm_pack_change": True,
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.industry_subcategory == "cafe"


def test_editing_subcategory_alone_does_not_clear_the_version():
    """Only a genuine pack switch invalidates the version."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = "healthcare"
    existing.industry_subcategory = "dental"
    existing.industry_pack_version = "1.0.0"
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_subcategory": "specialist"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.industry_subcategory == "specialist"
    assert existing.industry_pack_version == "1.0.0"


def test_repeating_the_same_industry_pack_is_not_a_change():
    """A settings form that resubmits every field must not trip the gate."""
    app, get_db = _make_app()
    existing = _fake_client("Pack Co")
    existing.industry_pack = "healthcare"
    existing.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"industry_pack": "healthcare", "industry_subcategory": "specialist"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.industry_subcategory == "specialist"


def test_update_client_allows_zero_score_drop_threshold():
    # "Set to 0 to disable" — the settings help text promises this, so 0 must be
    # accepted (the alert crossing test can never fire at 0).
    app, get_db = _make_app()
    existing = _fake_client("Threshold Co")

    def fake_refresh(obj):
        obj.score_drop_threshold = 0

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"score_drop_threshold": 0},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["score_drop_threshold"] == 0


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
    ("GET",   "/api/v1/clients/gap-matrix"),
    ("GET",   f"/api/v1/clients/{uuid.uuid4()}/command-center"),
])
def test_endpoints_require_auth(method, path):
    from app.main import app
    client = TestClient(app)
    response = client.request(method, path, json={})
    assert response.status_code == 401


def test_get_gap_matrix_returns_200_with_matrix():
    """
    GET /api/v1/clients/gap-matrix returns 200 with categories and rows.
    Also proves route ordering: a 422 would indicate FastAPI parsed 'gap-matrix'
    as a /{client_id} UUID path param instead of hitting the dedicated route.
    """
    from unittest.mock import patch
    from app.schemas.gap_matrix import GapMatrixResponse, GapMatrixRow, GapCell

    row_id = uuid.uuid4()
    fake_matrix = GapMatrixResponse(
        categories=["recommendation", "local"],
        rows=[
            GapMatrixRow(
                client_id=row_id,
                client_name="Acme",
                cells=[
                    GapCell(
                        category="recommendation",
                        competitors_winning=True,
                        top_competitor_name="Rival",
                        client_visibility=0.0,
                        top_competitor_visibility=100.0,
                    )
                ],
            )
        ],
    )

    app, get_db = _make_app()
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.clients.compute_gap_matrix", return_value=fake_matrix):
        client = TestClient(app)
        response = client.get("/api/v1/clients/gap-matrix")

    app.dependency_overrides.clear()

    assert response.status_code == 200, f"Expected 200, got {response.status_code} (422 = route ordering bug)"
    body = response.json()
    assert body["categories"] == ["recommendation", "local"]
    assert len(body["rows"]) == 1
    assert body["rows"][0]["client_name"] == "Acme"
    assert body["rows"][0]["cells"][0]["competitors_winning"] is True
    assert body["rows"][0]["cells"][0]["top_competitor_name"] == "Rival"


def _fake_command_center():
    from app.schemas.command_center import (
        AttentionSummary,
        CommandCenterAction,
        CommandCenterMetrics,
        CommandCenterResponse,
        DeliverySummary,
        MetricValue,
        PeriodStory,
    )

    return CommandCenterResponse(
        metrics=CommandCenterMetrics(
            ai_presence=MetricValue(value=45.0, delta=15.0, evidence_label="Observed"),
            accuracy=MetricValue(value=None, delta=None, evidence_label="Unavailable"),
            growth_readiness=MetricValue(value=60.0, delta=8.0, evidence_label="Composite (v1.4.0)"),
            business_impact=MetricValue(value=120.0, delta=40.0, evidence_label="Observed"),
        ),
        period_story=PeriodStory(
            headline="AI Presence improved by 15.0 points",
            bullets=["Growth Readiness up 8.0 points at 60.0"],
        ),
        attention=AttentionSummary(accuracy_risks=1, overdue_actions=0, stale_scan=False),
        delivery=DeliverySummary(in_progress=1, ready_to_publish=2, completed_last_30d=3),
        priority_actions=[
            CommandCenterAction(
                id=uuid.uuid4(),
                action_text="Publish the service page",
                priority="high",
                reason="Estimated +9.0 points to Growth Readiness",
            )
        ],
    )


def test_get_command_center_returns_200_with_full_contract():
    from unittest.mock import patch

    app, get_db = _make_app()
    existing = _fake_client("Acme Corp")
    existing.archived_at = None
    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.clients.build_command_center", return_value=_fake_command_center()):
        client = TestClient(app)
        response = client.get(f"/api/v1/clients/{existing.id}/command-center")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"metrics", "period_story", "attention", "delivery", "priority_actions"}
    assert body["metrics"]["ai_presence"] == {
        "value": 45.0, "delta": 15.0, "evidence_label": "Observed",
    }
    assert body["metrics"]["accuracy"]["value"] is None
    assert body["metrics"]["accuracy"]["evidence_label"] == "Unavailable"
    assert body["metrics"]["growth_readiness"]["evidence_label"] == "Composite (v1.4.0)"
    assert body["period_story"]["headline"] == "AI Presence improved by 15.0 points"
    assert body["attention"] == {"accuracy_risks": 1, "overdue_actions": 0, "stale_scan": False}
    # Three delivery fields only — nothing stored backs a "waiting for client" state.
    assert set(body["delivery"]) == {"in_progress", "ready_to_publish", "completed_last_30d"}
    assert body["priority_actions"][0]["action_text"] == "Publish the service page"
    assert set(body["priority_actions"][0]) == {"id", "action_text", "priority", "reason"}


def test_get_command_center_404_for_unknown_client():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get(f"/api/v1/clients/{uuid.uuid4()}/command-center")
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_get_command_center_404_for_archived_client():
    from datetime import datetime

    app, get_db = _make_app()
    archived = _fake_client("Gone Co")
    archived.archived_at = datetime(2026, 1, 1)
    mock_db = MagicMock()
    mock_db.get.return_value = archived
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get(f"/api/v1/clients/{archived.id}/command-center")
    app.dependency_overrides.clear()
    assert response.status_code == 404
