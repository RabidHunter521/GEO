"""Authenticated, client-scoped Conversion Event API contract."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.core.database import get_db
    from app.main import app

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


def _make_client(db, name="Acme Dental"):
    from app.models.client import Client

    account = Client(
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
    )
    db.add(account)
    db.commit()
    return account


def _event_payload(
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


def _import(client, client_id, headers, events):
    response = client.post(
        f"/api/v1/clients/{client_id}/conversion-events/import",
        headers=headers,
        json={"events": events},
    )
    return response


# --- Auth --------------------------------------------------------------


def test_conversion_event_routes_require_authentication(client, db):
    account = _make_client(db)

    assert (
        client.get(f"/api/v1/clients/{account.id}/conversion-events").status_code == 401
    )
    assert (
        client.get(f"/api/v1/clients/{account.id}/conversion-events/summary").status_code == 401
    )
    assert (
        client.post(
            f"/api/v1/clients/{account.id}/conversion-events/import",
            json={"events": [_event_payload()]},
        ).status_code
        == 401
    )


# --- Import --------------------------------------------------------------


def test_bulk_import_inserts_events(client, db, auth_headers):
    account = _make_client(db)

    response = _import(
        client,
        account.id,
        auth_headers,
        [_event_payload(external_event_id="ext-1"), _event_payload(external_event_id="ext-2")],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {"inserted": 2, "updated": 0, "total": 2}


def test_reimporting_the_same_batch_updates_instead_of_duplicating(client, db, auth_headers):
    account = _make_client(db)
    _import(client, account.id, auth_headers, [_event_payload(value_minor=1000)])

    response = _import(client, account.id, auth_headers, [_event_payload(value_minor=5000)])
    assert response.status_code == 201
    assert response.json() == {"inserted": 0, "updated": 1, "total": 1}

    listed = client.get(
        f"/api/v1/clients/{account.id}/conversion-events", headers=auth_headers
    )
    assert len(listed.json()) == 1
    assert listed.json()[0]["value_minor"] == 5000


def test_import_rejects_observed_event_missing_external_id(client, db, auth_headers):
    account = _make_client(db)

    response = _import(
        client,
        account.id,
        auth_headers,
        [_event_payload(evidence_level="observed", external_event_id=None)],
    )
    assert response.status_code == 422


def test_import_rejects_unsupported_currency(client, db, auth_headers):
    account = _make_client(db)

    response = _import(client, account.id, auth_headers, [_event_payload(currency="XYZ")])
    assert response.status_code == 422


def test_import_rejects_negative_value_for_non_estimated_event(client, db, auth_headers):
    account = _make_client(db)

    response = _import(
        client, account.id, auth_headers, [_event_payload(value_minor=-100)]
    )
    assert response.status_code == 422


def test_import_accepts_negative_value_for_estimated_event(client, db, auth_headers):
    account = _make_client(db)

    response = _import(
        client,
        account.id,
        auth_headers,
        [
            _event_payload(
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                value_minor=-500,
                calculation_method="refund_adjustment",
                calculation_version="v1",
            )
        ],
    )
    assert response.status_code == 201
    assert response.json()["inserted"] == 1


def test_import_returns_404_for_nonexistent_client(client, auth_headers):
    import uuid

    fake_client_id = uuid.uuid4()
    response = _import(client, fake_client_id, auth_headers, [_event_payload()])
    assert response.status_code == 404


# --- Listing ---------------------------------------------------------------


def test_list_events_is_paginated_and_filterable(client, db, auth_headers):
    account = _make_client(db)
    _import(
        client,
        account.id,
        auth_headers,
        [
            _event_payload(event_type="lead", external_event_id="ext-1"),
            _event_payload(event_type="booking", external_event_id="ext-2"),
        ],
    )

    all_events = client.get(
        f"/api/v1/clients/{account.id}/conversion-events", headers=auth_headers
    )
    assert all_events.status_code == 200
    assert len(all_events.json()) == 2

    filtered = client.get(
        f"/api/v1/clients/{account.id}/conversion-events?event_type=booking",
        headers=auth_headers,
    )
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["event_type"] == "booking"

    paginated = client.get(
        f"/api/v1/clients/{account.id}/conversion-events?limit=1&offset=0",
        headers=auth_headers,
    )
    assert len(paginated.json()) == 1


def test_list_does_not_leak_another_clients_rows(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    _import(client, account_a.id, auth_headers, [_event_payload(external_event_id="a")])
    _import(client, account_b.id, auth_headers, [_event_payload(external_event_id="b")])

    response = client.get(
        f"/api/v1/clients/{account_a.id}/conversion-events", headers=auth_headers
    )
    assert [row["external_event_id"] for row in response.json()] == ["a"]


def test_list_returns_404_for_nonexistent_client(client, auth_headers):
    import uuid

    fake_client_id = uuid.uuid4()
    response = client.get(
        f"/api/v1/clients/{fake_client_id}/conversion-events", headers=auth_headers
    )
    assert response.status_code == 404


# --- Summary -----------------------------------------------------------


def test_summary_endpoint_aggregates_by_evidence_level(client, db, auth_headers):
    account = _make_client(db)
    _import(
        client,
        account.id,
        auth_headers,
        [
            _event_payload(evidence_level="observed", external_event_id="o1", value_minor=1000),
            _event_payload(evidence_level="attributed", external_event_id="a1", value_minor=400),
            _event_payload(
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                value_minor=200,
                calculation_method="m",
                calculation_version="v1",
            ),
        ],
    )

    response = client.get(
        f"/api/v1/clients/{account.id}/conversion-events/summary", headers=auth_headers
    )
    assert response.status_code == 200
    summaries = response.json()
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["observed_value_minor"] == 1000
    assert summary["attributed_value_minor"] == 400
    assert summary["assisted_value_minor"] == 0
    assert summary["estimated_value_minor"] == 200
    assert summary["currency"] == "MYR"


def test_summary_splits_by_currency(client, db, auth_headers):
    account = _make_client(db)
    _import(
        client,
        account.id,
        auth_headers,
        [
            _event_payload(currency="MYR", external_event_id="myr-1", value_minor=1000),
            _event_payload(currency="USD", external_event_id="usd-1", value_minor=250),
        ],
    )

    response = client.get(
        f"/api/v1/clients/{account.id}/conversion-events/summary", headers=auth_headers
    )
    summaries = response.json()
    currencies = {row["currency"] for row in summaries}
    assert currencies == {"MYR", "USD"}


def test_summary_returns_404_for_nonexistent_client(client, auth_headers):
    import uuid

    fake_client_id = uuid.uuid4()
    response = client.get(
        f"/api/v1/clients/{fake_client_id}/conversion-events/summary", headers=auth_headers
    )
    assert response.status_code == 404
