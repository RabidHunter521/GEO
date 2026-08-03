"""Authenticated, client-scoped Business Location API contract."""

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


def _payload(name="Orchard Clinic", **overrides):
    body = {"name": name, "country": "SG", "latitude": 1.3048, "longitude": 103.8318}
    body.update(overrides)
    return body


def _create_location(client, client_id, headers, name="Orchard Clinic", **overrides):
    response = client.post(
        f"/api/v1/clients/{client_id}/locations",
        headers=headers,
        json=_payload(name, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_location_routes_require_authentication(client, db):
    account = _make_client(db)

    assert client.get(f"/api/v1/clients/{account.id}/locations").status_code == 401
    assert client.post(f"/api/v1/clients/{account.id}/locations", json=_payload()).status_code == 401


def test_create_list_get_patch_and_deactivate_location(client, db, auth_headers):
    account = _make_client(db)
    created = _create_location(client, account.id, auth_headers, is_primary=True)

    assert created["slug"] == "orchard-clinic"
    assert created["active"] is True
    assert client.get(f"/api/v1/clients/{account.id}/locations", headers=auth_headers).json() == [created]

    fetched = client.get(
        f"/api/v1/clients/{account.id}/locations/{created['id']}", headers=auth_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]

    patched = client.patch(
        f"/api/v1/clients/{account.id}/locations/{created['id']}",
        headers=auth_headers,
        json={"city": "Singapore", "booking_url": "https://example.com/book"},
    )
    assert patched.status_code == 200
    assert patched.json()["city"] == "Singapore"

    deleted = client.delete(
        f"/api/v1/clients/{account.id}/locations/{created['id']}", headers=auth_headers
    )
    assert deleted.status_code == 422  # the only active location remains protected

    _create_location(client, account.id, auth_headers, "Tampines Clinic")
    deleted = client.delete(
        f"/api/v1/clients/{account.id}/locations/{created['id']}", headers=auth_headers
    )
    assert deleted.status_code == 204
    active = client.get(f"/api/v1/clients/{account.id}/locations", headers=auth_headers)
    assert active.status_code == 200
    assert [row["name"] for row in active.json()] == ["Tampines Clinic"]
    inactive = client.get(
        f"/api/v1/clients/{account.id}/locations", headers=auth_headers, params={"active": False}
    )
    assert inactive.status_code == 200
    assert inactive.json()[0]["id"] == created["id"]
    assert inactive.json()[0]["active"] is False


def test_location_routes_hide_other_clients_locations_and_validate_coordinates(
    client, db, auth_headers
):
    account = _make_client(db)
    other = _make_client(db, "Bravo Legal")
    created = _create_location(client, account.id, auth_headers)

    for method in ("get", "patch", "delete"):
        response = getattr(client, method)(
            f"/api/v1/clients/{other.id}/locations/{created['id']}",
            headers=auth_headers,
            **({"json": {"city": "Elsewhere"}} if method == "patch" else {}),
        )
        assert response.status_code == 404

    invalid = client.post(
        f"/api/v1/clients/{account.id}/locations",
        headers=auth_headers,
        json=_payload(latitude=-90.1),
    )
    assert invalid.status_code == 422


def test_primary_location_is_reassigned_through_the_api(client, db, auth_headers):
    account = _make_client(db)
    first = _create_location(client, account.id, auth_headers, "Orchard", is_primary=True)
    second = _create_location(client, account.id, auth_headers, "Tampines")

    response = client.patch(
        f"/api/v1/clients/{account.id}/locations/{second['id']}",
        headers=auth_headers,
        json={"is_primary": True},
    )

    assert response.status_code == 200
    locations = client.get(f"/api/v1/clients/{account.id}/locations", headers=auth_headers).json()
    assert {item["id"]: item["is_primary"] for item in locations} == {
        first["id"]: False,
        second["id"]: True,
    }
