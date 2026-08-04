"""Authenticated, client-scoped Search Console signal import/query API
contract."""

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


def _signal_payload(**overrides):
    body = {
        "property_uri": "sc-domain:example.com",
        "signal_date": "2026-08-01",
        "query": "best dentist in kl",
        "page": "https://example.com/",
        "clicks": 10,
        "impressions": 100,
        "ctr": 0.1,
        "position": 4.5,
    }
    body.update(overrides)
    return body


def _sync(client, client_id, headers, signals):
    return client.post(
        f"/api/v1/clients/{client_id}/search-console/sync",
        headers=headers,
        json={"signals": signals},
    )


# --- Auth -------------------------------------------------------------


def test_search_console_routes_require_authentication(client, db):
    account = _make_client(db)

    assert (
        client.get(f"/api/v1/clients/{account.id}/search-console/status").status_code == 401
    )
    assert (
        client.get(f"/api/v1/clients/{account.id}/search-console/signals").status_code == 401
    )
    assert (
        client.post(
            f"/api/v1/clients/{account.id}/search-console/sync",
            json={"signals": [_signal_payload()]},
        ).status_code
        == 401
    )


# --- 404 on missing client ----------------------------------------------


def test_operations_against_a_nonexistent_client_return_404(client, auth_headers):
    import uuid

    fake_client_id = uuid.uuid4()
    assert (
        client.get(
            f"/api/v1/clients/{fake_client_id}/search-console/status", headers=auth_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/clients/{fake_client_id}/search-console/signals", headers=auth_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/clients/{fake_client_id}/search-console/sync",
            headers=auth_headers,
            json={"signals": [_signal_payload()]},
        ).status_code
        == 404
    )


# --- Bulk sync -----------------------------------------------------------


def test_sync_inserts_then_updates_on_repeated_call(client, db, auth_headers):
    account = _make_client(db)

    first = _sync(client, account.id, auth_headers, [_signal_payload()])
    assert first.status_code == 200, first.text
    assert first.json() == {"inserted": 1, "updated": 0, "skipped": 0, "total": 1}

    second = _sync(client, account.id, auth_headers, [_signal_payload(clicks=99)])
    assert second.status_code == 200
    assert second.json() == {"inserted": 0, "updated": 1, "skipped": 0, "total": 1}


def test_sync_rejects_empty_batch(client, db, auth_headers):
    account = _make_client(db)

    response = _sync(client, account.id, auth_headers, [])
    assert response.status_code == 422


def test_sync_rejects_unknown_fields(client, db, auth_headers):
    account = _make_client(db)

    response = client.post(
        f"/api/v1/clients/{account.id}/search-console/sync",
        headers=auth_headers,
        json={"signals": [_signal_payload(access_token="secret")]},
    )
    assert response.status_code == 422


def test_sync_returns_404_for_a_location_from_another_client(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)

    response = _sync(
        client,
        account_a.id,
        auth_headers,
        [_signal_payload(location_id=str(foreign_location.id))],
    )
    assert response.status_code == 404


# --- Paginated listing -----------------------------------------------------


def test_list_signals_returns_synced_rows(client, db, auth_headers):
    account = _make_client(db)
    _sync(
        client,
        account.id,
        auth_headers,
        [
            _signal_payload(page="https://example.com/a", query="dentist kl"),
            _signal_payload(page="https://example.com/b", query="lawyer kl"),
        ],
    )

    response = client.get(
        f"/api/v1/clients/{account.id}/search-console/signals", headers=auth_headers
    )
    assert response.status_code == 200
    assert {row["query"] for row in response.json()} == {"dentist kl", "lawyer kl"}


def test_list_signals_filters_by_query(client, db, auth_headers):
    account = _make_client(db)
    _sync(
        client,
        account.id,
        auth_headers,
        [
            _signal_payload(page="https://example.com/a", query="dentist kl"),
            _signal_payload(page="https://example.com/b", query="lawyer kl"),
        ],
    )

    response = client.get(
        f"/api/v1/clients/{account.id}/search-console/signals?query=dentist",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert [row["query"] for row in response.json()] == ["dentist kl"]


def test_list_signals_respects_limit(client, db, auth_headers):
    account = _make_client(db)
    _sync(
        client,
        account.id,
        auth_headers,
        [
            _signal_payload(page="https://example.com/a", signal_date="2026-08-01"),
            _signal_payload(page="https://example.com/b", signal_date="2026-08-02"),
            _signal_payload(page="https://example.com/c", signal_date="2026-08-03"),
        ],
    )

    response = client.get(
        f"/api/v1/clients/{account.id}/search-console/signals?limit=1",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_does_not_leak_another_clients_rows(client, db, auth_headers):
    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    _sync(client, account_a.id, auth_headers, [_signal_payload(query="query a")])
    _sync(client, account_b.id, auth_headers, [_signal_payload(query="query b")])

    response = client.get(
        f"/api/v1/clients/{account_a.id}/search-console/signals", headers=auth_headers
    )
    assert [row["query"] for row in response.json()] == ["query a"]


# --- Status summary ---------------------------------------------------


def test_status_reflects_synced_data(client, db, auth_headers):
    account = _make_client(db)
    _sync(
        client,
        account.id,
        auth_headers,
        [
            _signal_payload(signal_date="2026-07-01"),
            _signal_payload(signal_date="2026-08-01", page="https://example.com/other"),
        ],
    )

    response = client.get(
        f"/api/v1/clients/{account.id}/search-console/status", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_signals"] == 2
    assert body["earliest_signal_date"] == "2026-07-01"
    assert body["latest_signal_date"] == "2026-08-01"
    assert body["property_uris"] == ["sc-domain:example.com"]
    assert body["last_synced_at"] is not None


def test_status_for_client_with_no_signals(client, db, auth_headers):
    account = _make_client(db)

    response = client.get(
        f"/api/v1/clients/{account.id}/search-console/status", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_signals"] == 0
    assert body["property_uris"] == []
    assert body["earliest_signal_date"] is None
    assert body["latest_signal_date"] is None
    assert body["last_synced_at"] is None
