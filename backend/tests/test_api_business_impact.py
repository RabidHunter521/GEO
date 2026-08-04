"""API contract for the business-impact evidence ladder:

- Admin endpoint `GET /clients/{client_id}/business-impact` — authenticated,
  returns the full `ImpactSummary` shape.
- Client-view endpoint `GET /view/{token}/business-impact` — token-gated,
  returns the whitelisted `ImpactSummaryPublic` shape and omits admin-only
  fields.
"""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app


# --- shared helpers ------------------------------------------------------------


def _make_client(db, *, is_prospect=False, name="Acme Dental"):
    from app.models.client import Client

    client = Client(
        id=uuid.uuid4(),
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
        share_token=uuid.uuid4().hex,
        scan_cadence_days=30,
        is_prospect=is_prospect,
    )
    db.add(client)
    db.flush()
    db.commit()
    return client


def _event(
    event_type="lead",
    source="manual",
    evidence_level="observed",
    external_event_id="ext-1",
    occurred_at="2026-07-01T00:00:00Z",
    value_minor=1000,
    currency="MYR",
    **overrides,
):
    body = dict(
        event_type=event_type,
        source=source,
        evidence_level=evidence_level,
        external_event_id=external_event_id,
        occurred_at=occurred_at,
        value_minor=value_minor,
        currency=currency,
    )
    body.update(overrides)
    return body


def _import_via_service(db, client_id, events_json):
    """Import through the schema/service layer directly (avoids depending on
    the conversion-events API being wired up in the same TestClient call)."""
    from app.schemas.conversion_event import ConversionEventCreate
    from app.services import conversion_evidence_service

    payloads = []
    for event in events_json:
        occurred_at = event.get("occurred_at")
        if isinstance(occurred_at, str):
            event = {**event, "occurred_at": datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))}
        payloads.append(ConversionEventCreate(**event))
    conversion_evidence_service.import_events(client_id, payloads, db)


# --- Admin endpoint ------------------------------------------------------------


@pytest.fixture
def admin_client(db):
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings

    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


def test_admin_endpoint_requires_authentication(admin_client, db):
    account = _make_client(db)
    response = admin_client.get(f"/api/v1/clients/{account.id}/business-impact")
    assert response.status_code == 401


def test_admin_endpoint_returns_404_for_nonexistent_client(admin_client, auth_headers):
    fake_client_id = uuid.uuid4()
    response = admin_client.get(
        f"/api/v1/clients/{fake_client_id}/business-impact", headers=auth_headers
    )
    assert response.status_code == 404


def test_admin_endpoint_returns_impact_summary_per_currency(admin_client, db, auth_headers):
    account = _make_client(db)
    _import_via_service(
        db,
        account.id,
        [
            _event(currency="MYR", external_event_id="myr-1", value_minor=1000),
            _event(currency="USD", external_event_id="usd-1", value_minor=250),
        ],
    )

    response = admin_client.get(
        f"/api/v1/clients/{account.id}/business-impact", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    currencies = {row["currency"] for row in body}
    assert currencies == {"MYR", "USD"}
    for row in body:
        assert row["calculation_version"] == "impact_v1"
        assert "Values are separated by evidence level" in " ".join(row["caveats"])


def test_admin_endpoint_applies_date_filters(admin_client, db, auth_headers):
    account = _make_client(db)
    _import_via_service(
        db,
        account.id,
        [
            _event(external_event_id="jan", occurred_at="2026-01-15T00:00:00Z"),
            _event(external_event_id="jul", occurred_at="2026-07-15T00:00:00Z"),
        ],
    )

    response = admin_client.get(
        f"/api/v1/clients/{account.id}/business-impact"
        "?date_from=2026-06-01&date_to=2026-08-01",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["observed_value_minor"] == 1000
    assert body[0]["window_start"] == "2026-06-01"
    assert body[0]["window_end"] == "2026-08-01"


def test_admin_endpoint_returns_empty_list_for_client_with_no_events(
    admin_client, db, auth_headers
):
    account = _make_client(db)
    response = admin_client.get(
        f"/api/v1/clients/{account.id}/business-impact", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == []


# --- Client-view endpoint --------------------------------------------------------


@pytest.fixture
def view_client(db):
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_view_endpoint_requires_a_valid_token(view_client, db):
    _make_client(db)
    response = view_client.get(f"/api/v1/view/{'x' * 32}/business-impact")
    assert response.status_code == 404


def test_view_endpoint_returns_404_for_prospect(view_client, db):
    account = _make_client(db, is_prospect=True)
    response = view_client.get(f"/api/v1/view/{account.share_token}/business-impact")
    assert response.status_code == 404


def test_view_endpoint_returns_public_shape(view_client, db):
    account = _make_client(db)
    _import_via_service(
        db,
        account.id,
        [
            _event(evidence_level="observed", external_event_id="o1", value_minor=1000),
            _event(
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                value_minor=200,
                calculation_method="linear_projection",
                calculation_version="v1",
                notes="internal note",
            ),
        ],
    )

    response = view_client.get(f"/api/v1/view/{account.share_token}/business-impact")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["observed_value_minor"] == 1000
    assert row["estimated_value_minor"] == 200
    assert row["currency"] == "MYR"
    assert any("modeled projections" in c for c in row["caveats"])

    # Admin-only fields must never appear on the public shape.
    for forbidden in (
        "calculation_version",
        "metadata_json",
        "calculation_method",
        "notes",
        "external_event_id",
    ):
        assert forbidden not in row


def test_view_endpoint_applies_date_filters(view_client, db):
    account = _make_client(db)
    _import_via_service(
        db,
        account.id,
        [
            _event(external_event_id="jan", occurred_at="2026-01-15T00:00:00Z"),
            _event(external_event_id="jul", occurred_at="2026-07-15T00:00:00Z"),
        ],
    )

    response = view_client.get(
        f"/api/v1/view/{account.share_token}/business-impact"
        "?date_from=2026-06-01&date_to=2026-08-01"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["observed_value_minor"] == 1000


def test_view_endpoint_empty_for_client_with_no_events(view_client, db):
    account = _make_client(db)
    response = view_client.get(f"/api/v1/view/{account.share_token}/business-impact")
    assert response.status_code == 200
    assert response.json() == []
