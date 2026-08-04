"""Authenticated, client-scoped Tracked Query API contract."""

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


def _make_location(db, client_id, name="Orchard Clinic"):
    from app.services.business_location_service import create_location
    from app.schemas.business_location import BusinessLocationCreate

    return create_location(
        client_id,
        BusinessLocationCreate(name=name, country="SG", latitude=1.3048, longitude=103.8318),
        db,
    )


def _payload(text="Best dentist in KL", **overrides):
    body = {"text": text, "source": "manual", "intent": "recommendation"}
    body.update(overrides)
    return body


def _create(client, client_id, headers, text="Best dentist in KL", **overrides):
    response = client.post(
        f"/api/v1/clients/{client_id}/tracked-queries",
        headers=headers,
        json=_payload(text, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Auth -------------------------------------------------------------


def test_tracked_query_routes_require_authentication(client, db):
    account = _make_client(db)

    assert client.get(f"/api/v1/clients/{account.id}/tracked-queries").status_code == 401
    assert (
        client.post(f"/api/v1/clients/{account.id}/tracked-queries", json=_payload()).status_code
        == 401
    )


# --- Create / list / patch / archive happy path -------------------------


def test_create_list_patch_and_archive_tracked_query(client, db, auth_headers):
    account = _make_client(db)
    created = _create(client, account.id, auth_headers)

    assert created["normalized_text"] == "best dentist in kl"
    assert created["is_active"] is True
    assert created["priority_reasons"] == []

    listed = client.get(f"/api/v1/clients/{account.id}/tracked-queries", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json() == [created]

    patched = client.patch(
        f"/api/v1/clients/{account.id}/tracked-queries/{created['id']}",
        headers=auth_headers,
        json={"demand_weight": 0.9},
    )
    assert patched.status_code == 200
    assert patched.json()["demand_weight"] == 0.9
    assert patched.json()["priority_score"] != created["priority_score"]

    archived = client.post(
        f"/api/v1/clients/{account.id}/tracked-queries/{created['id']}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False

    active_listing = client.get(
        f"/api/v1/clients/{account.id}/tracked-queries", headers=auth_headers
    )
    assert active_listing.json() == []

    inactive_listing = client.get(
        f"/api/v1/clients/{account.id}/tracked-queries?active=false", headers=auth_headers
    )
    assert [row["id"] for row in inactive_listing.json()] == [created["id"]]


def test_create_returns_409_on_duplicate_text(client, db, auth_headers):
    account = _make_client(db)
    _create(client, account.id, auth_headers, "Best dentist in KL")

    duplicate = client.post(
        f"/api/v1/clients/{account.id}/tracked-queries",
        headers=auth_headers,
        json=_payload("  BEST DENTIST   in KL "),
    )
    assert duplicate.status_code == 409


# --- Cross-client denial -------------------------------------------------


def test_cannot_patch_another_clients_tracked_query(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    created = _create(client, account_a.id, auth_headers)

    response = client.patch(
        f"/api/v1/clients/{account_b.id}/tracked-queries/{created['id']}",
        headers=auth_headers,
        json={"demand_weight": 0.9},
    )
    assert response.status_code == 404


def test_cannot_archive_another_clients_tracked_query(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    created = _create(client, account_a.id, auth_headers)

    response = client.post(
        f"/api/v1/clients/{account_b.id}/tracked-queries/{created['id']}/archive",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_list_does_not_leak_another_clients_rows(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    _create(client, account_a.id, auth_headers, "Query A")
    _create(client, account_b.id, auth_headers, "Query B")

    response = client.get(f"/api/v1/clients/{account_a.id}/tracked-queries", headers=auth_headers)
    assert [row["text"] for row in response.json()] == ["Query A"]


# --- Location ownership ---------------------------------------------------


def test_create_rejects_a_location_from_another_client(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)

    response = client.post(
        f"/api/v1/clients/{account_a.id}/tracked-queries",
        headers=auth_headers,
        json=_payload(location_id=str(foreign_location.id)),
    )
    assert response.status_code == 404


def test_create_accepts_a_location_owned_by_the_same_client(client, db, auth_headers):
    account = _make_client(db)
    location = _make_location(db, account.id)

    response = client.post(
        f"/api/v1/clients/{account.id}/tracked-queries",
        headers=auth_headers,
        json=_payload(location_id=str(location.id)),
    )
    assert response.status_code == 201
    assert response.json()["location_id"] == str(location.id)


# --- Priority scoring is server-computed -----------------------------------


def test_client_cannot_set_priority_score_directly(client, db, auth_headers):
    account = _make_client(db)

    response = client.post(
        f"/api/v1/clients/{account.id}/tracked-queries",
        headers=auth_headers,
        json=_payload(priority_score=999),
    )
    # extra="forbid" on the schema rejects the unknown field outright.
    assert response.status_code == 422


def test_priority_reasons_reflect_notable_drivers(client, db, auth_headers):
    account = _make_client(db)
    created = _create(
        client,
        account.id,
        auth_headers,
        "High priority query",
        demand_weight=0.95,
        buyer_stage="decision",
        risk_level="critical",
    )
    assert created["priority_reasons"] != []


# --- Nonexistent client -----------------------------------------------------


def test_operations_against_a_nonexistent_client_return_404(client, auth_headers):
    import uuid

    fake_client_id = uuid.uuid4()
    assert (
        client.get(f"/api/v1/clients/{fake_client_id}/tracked-queries", headers=auth_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/clients/{fake_client_id}/tracked-queries", headers=auth_headers, json=_payload()
        ).status_code
        == 404
    )
