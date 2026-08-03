"""Authenticated administrative API contract for versioned truth facts."""

from datetime import datetime

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


def _make_location(db, client_id, name="Orchard"):
    from app.models.business_location import BusinessLocation

    location = BusinessLocation(client_id=client_id, name=name, slug=name.lower())
    db.add(location)
    db.commit()
    return location


def _fact_payload(fact_key="phone", **overrides):
    body = {"fact_type": "business", "fact_key": fact_key}
    body.update(overrides)
    return body


def _version_payload(value="+65 1111 1111", **overrides):
    body = {
        "value": {"value": value, "display_value": value},
        "source_url": "https://acme.example/contact",
        "reviewer_note": "Checked against the client record.",
        "effective_from": "2026-01-01T09:00:00",
    }
    body.update(overrides)
    return body


def _create_fact(client, client_id, headers, fact_key="phone", **overrides):
    response = client.post(
        f"/api/v1/clients/{client_id}/truth-facts",
        headers=headers,
        json=_fact_payload(fact_key, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _draft_version(client, client_id, fact_id, headers, **overrides):
    response = client.post(
        f"/api/v1/clients/{client_id}/truth-facts/{fact_id}/versions",
        headers=headers,
        json=_version_payload(**overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve_version(client, client_id, fact_id, version_id, headers):
    response = client.post(
        f"/api/v1/clients/{client_id}/truth-facts/{fact_id}/approve/{version_id}",
        headers=headers,
        json={"approved_by": "reviewer@example.com"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_truth_vault_routes_require_admin_authentication(client, db):
    account = _make_client(db)
    fact_id = "00000000-0000-0000-0000-000000000001"
    version_id = "00000000-0000-0000-0000-000000000002"
    base = f"/api/v1/clients/{account.id}/truth-facts"

    requests = (
        ("get", base, {}),
        ("post", base, {"json": _fact_payload()}),
        ("get", f"{base}/{fact_id}", {}),
        ("post", f"{base}/{fact_id}/versions", {"json": _version_payload()}),
        ("post", f"{base}/{fact_id}/approve/{version_id}", {"json": {"approved_by": "Maya"}}),
        ("post", f"{base}/{fact_id}/retire", {"json": {"effective_at": "2026-02-01T09:00:00"}}),
    )

    for method, url, kwargs in requests:
        assert getattr(client, method)(url, **kwargs).status_code == 401


def test_truth_facts_keep_brand_and_location_scopes_separate_in_current_and_history_modes(
    client, db, auth_headers
):
    account = _make_client(db)
    location = _make_location(db, account.id)
    brand_fact = _create_fact(client, account.id, auth_headers, "phone")
    location_fact = _create_fact(
        client,
        account.id,
        auth_headers,
        "phone",
        fact_type="location",
        location_id=str(location.id),
    )
    first = _draft_version(client, account.id, brand_fact["id"], auth_headers)
    _approve_version(client, account.id, brand_fact["id"], first["id"], auth_headers)
    _draft_version(client, account.id, brand_fact["id"], auth_headers, value="+65 2222 2222")
    location_version = _draft_version(client, account.id, location_fact["id"], auth_headers)
    _approve_version(client, account.id, location_fact["id"], location_version["id"], auth_headers)

    brand_current = client.get(
        f"/api/v1/clients/{account.id}/truth-facts", headers=auth_headers
    )
    assert brand_current.status_code == 200
    assert brand_current.json()["total"] == 1
    assert brand_current.json()["facts"][0]["id"] == brand_fact["id"]
    assert [version["status"] for version in brand_current.json()["facts"][0]["versions"]] == [
        "approved"
    ]

    location_current = client.get(
        f"/api/v1/clients/{account.id}/truth-facts",
        headers=auth_headers,
        params={"location_id": str(location.id)},
    )
    assert location_current.status_code == 200
    assert [fact["id"] for fact in location_current.json()["facts"]] == [location_fact["id"]]

    history = client.get(
        f"/api/v1/clients/{account.id}/truth-facts",
        headers=auth_headers,
        params={"mode": "history"},
    )
    assert history.status_code == 200
    assert [version["status"] for version in history.json()["facts"][0]["versions"]] == [
        "draft",
        "approved",
    ]


def test_truth_fact_lifecycle_validates_urls_and_hides_cross_client_resources(
    client, db, auth_headers
):
    account = _make_client(db)
    other = _make_client(db, "Bravo Legal")
    other_location = _make_location(db, other.id)
    fact = _create_fact(client, account.id, auth_headers)

    for invalid_source_url in (
        "not a URL",
        "https://acme.example:99999/contact",
        "https://acme\n.example/contact",
        "https://acme\u0085.example/contact",
    ):
        invalid_url = client.post(
            f"/api/v1/clients/{account.id}/truth-facts/{fact['id']}/versions",
            headers=auth_headers,
            json=_version_payload(source_url=invalid_source_url),
        )
        assert invalid_url.status_code == 422
    assert client.post(
        f"/api/v1/clients/{account.id}/truth-facts",
        headers=auth_headers,
        json=_fact_payload("address", location_id=str(other_location.id)),
    ).status_code == 404

    draft = _draft_version(client, account.id, fact["id"], auth_headers)
    for method, suffix, body in (
        ("get", "", None),
        ("post", "/versions", _version_payload()),
        ("post", f"/approve/{draft['id']}", {"approved_by": "Maya"}),
        ("post", "/retire", {"effective_at": "2026-02-01T09:00:00"}),
    ):
        response = getattr(client, method)(
            f"/api/v1/clients/{other.id}/truth-facts/{fact['id']}{suffix}",
            headers=auth_headers,
            **({"json": body} if body is not None else {}),
        )
        assert response.status_code == 404

    approved = _approve_version(client, account.id, fact["id"], draft["id"], auth_headers)
    assert approved["status"] == "approved"
    retired = client.post(
        f"/api/v1/clients/{account.id}/truth-facts/{fact['id']}/retire",
        headers=auth_headers,
        json={"effective_at": "2026-02-01T09:00:00"},
    )
    assert retired.status_code == 200
    assert retired.json()["effective_to"] == "2026-02-01T08:59:59.999999"


@pytest.mark.parametrize(
    "source_url",
    [
        "http://acme.example/contact",
        "https://acme.example/contact",
        "https://b" "\u00fc" "cher.example/contact",
    ],
)
def test_truth_fact_versions_accept_valid_http_and_unicode_source_urls(
    client, db, auth_headers, source_url
):
    account = _make_client(db)
    fact = _create_fact(client, account.id, auth_headers)

    response = client.post(
        f"/api/v1/clients/{account.id}/truth-facts/{fact['id']}/versions",
        headers=auth_headers,
        json=_version_payload(source_url=source_url),
    )

    assert response.status_code == 201
    assert isinstance(response.json()["source_url"], str)


def test_source_url_schema_rejects_c1_controls_when_the_url_adapter_is_permissive(monkeypatch):
    from pydantic import ValidationError

    from app.schemas import truth_fact

    class PermissiveUrlAdapter:
        def validate_python(self, value):
            return value

    monkeypatch.setattr(truth_fact, "TypeAdapter", lambda _url_type: PermissiveUrlAdapter())

    with pytest.raises(ValidationError):
        truth_fact.TruthFactVersionDraft(
            value={"value": "x", "display_value": "x"},
            source_url="https://acme\u0085.example/contact",
            effective_from=datetime(2026, 1, 1, 9, 0, 0),
        )


def test_truth_facts_paginate_and_reject_unknown_list_modes(client, db, auth_headers):
    from app.schemas.truth_fact import TruthFactCreate, TruthFactVersionDraft
    from app.services import truth_vault_service

    account = _make_client(db)
    for index in range(3):
        fact = truth_vault_service.create_fact(
            account.id, TruthFactCreate(fact_type="business", fact_key=f"field-{index}"), db
        )
        draft = truth_vault_service.draft_version(
            fact,
            TruthFactVersionDraft(
                value={"value": str(index), "display_value": str(index)},
                effective_from=datetime(2026, 1, 1, 9, 0, 0),
            ),
            db,
        )
        truth_vault_service.approve_version(fact.id, draft.id, "reviewer@example.com", db)

    page = client.get(
        f"/api/v1/clients/{account.id}/truth-facts",
        headers=auth_headers,
        params={"page": 2, "page_size": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["facts"]) == 1
    assert client.get(
        f"/api/v1/clients/{account.id}/truth-facts",
        headers=auth_headers,
        params={"mode": "all"},
    ).status_code == 422
