"""Authenticated Outcome Action API contract."""

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


def _make_client(db, name="Acme Dental", archived=False):
    from app.core.time import utcnow
    from app.models.client import Client

    row = Client(
        name=name,
        website=f"https://{name.replace(' ', '').lower()}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
    )
    if archived:
        row.archived_at = utcnow()
    db.add(row)
    db.commit()
    return row


def _payload(source_ref="content-gap:emergency", **overrides):
    body = {
        "source_kind": "content_gap",
        "source_ref": source_ref,
        "title": "Publish emergency dental page",
        "rationale": "Competitors currently win high-intent emergency searches.",
        "action_type": "content",
        "priority": "low",
        "confidence": "repeated",
        "client_safe_summary": "Create an emergency dental page.",
    }
    body.update(overrides)
    return body


def _create_action(client, client_id, headers, source_ref="content-gap:emergency", **overrides):
    response = client.post(
        f"/api/v1/clients/{client_id}/outcome-actions",
        headers=headers,
        json=_payload(source_ref, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_routes_require_authentication(client, db):
    account = _make_client(db)

    assert client.get(f"/api/v1/clients/{account.id}/outcome-actions").status_code == 401
    assert client.post(
        f"/api/v1/clients/{account.id}/outcome-actions", json=_payload()
    ).status_code == 401
    assert client.get("/api/v1/outcome-actions/review-queue").status_code == 401


def test_create_and_get_action_return_admin_decision_context_without_approval_evidence(
    client, db, auth_headers
):
    account = _make_client(db)
    created = _create_action(client, account.id, auth_headers)

    assert created["client_id"] == str(account.id)
    assert created["priority"] != "low"  # priority is server-owned
    assert created["rationale"] == "Competitors currently win high-intent emergency searches."
    assert created["source_kind"] == "content_gap"
    assert created["source_ref"] == "content-gap:emergency"
    assert isinstance(created["priority_reasons"]["reasons"], list)
    assert created["verification_result"] is None
    assert "approval_evidence" not in created
    assert "approval_evidence_hash" not in created

    fetched = client.get(
        f"/api/v1/clients/{account.id}/outcome-actions/{created['id']}", headers=auth_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_actions_are_scoped_to_active_client(client, db, auth_headers):
    account = _make_client(db)
    other = _make_client(db, "Bravo Legal")
    created = _create_action(client, account.id, auth_headers)

    for method, suffix, kwargs in (
        ("get", "", {}),
        ("patch", "", {"json": {"owner": "Maya"}}),
        ("post", "/transition", {"json": {"status": "in_progress"}}),
    ):
        response = getattr(client, method)(
            f"/api/v1/clients/{other.id}/outcome-actions/{created['id']}{suffix}",
            headers=auth_headers,
            **kwargs,
        )
        assert response.status_code == 404


def test_list_filters_by_status_due_date_and_paginates(client, db, auth_headers):
    account = _make_client(db)
    first = _create_action(
        client, account.id, auth_headers, "content-gap:first", due_date="2026-08-01"
    )
    second = _create_action(
        client, account.id, auth_headers, "content-gap:second", due_date="2026-08-15"
    )
    _create_action(client, account.id, auth_headers, "content-gap:third", due_date="2026-09-01")
    client.post(
        f"/api/v1/clients/{account.id}/outcome-actions/{second['id']}/transition",
        headers=auth_headers,
        json={"status": "approved_internal"},
    )

    filtered = client.get(
        f"/api/v1/clients/{account.id}/outcome-actions",
        headers=auth_headers,
        params={"status": "recommended", "due_from": "2026-08-01", "due_to": "2026-08-31"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert [row["id"] for row in filtered.json()["actions"]] == [first["id"]]

    page = client.get(
        f"/api/v1/clients/{account.id}/outcome-actions",
        headers=auth_headers,
        params={"page": 2, "page_size": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["actions"]) == 1

    assert client.get(
        f"/api/v1/clients/{account.id}/outcome-actions",
        headers=auth_headers,
        params={"page_size": 101},
    ).status_code == 422


def test_location_filtered_list_delegates_to_the_outcome_action_service(
    client, db, auth_headers, monkeypatch
):
    from app.models.business_location import BusinessLocation
    from app.services import outcome_action_service

    account = _make_client(db)
    location = BusinessLocation(client_id=account.id, name="Orchard", slug="orchard")
    db.add(location)
    db.commit()
    created = _create_action(client, account.id, auth_headers, location_id=str(location.id))
    calls = []
    original_list_actions = outcome_action_service.list_actions

    def record_list_actions(client_id, db_session, **kwargs):
        calls.append((client_id, kwargs))
        return original_list_actions(client_id, db_session, **kwargs)

    monkeypatch.setattr(outcome_action_service, "list_actions", record_list_actions)

    response = client.get(
        f"/api/v1/clients/{account.id}/outcome-actions",
        headers=auth_headers,
        params={"location_id": str(location.id)},
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["actions"]] == [created["id"]]
    assert calls == [
        (
            account.id,
            {"status": None, "location_id": location.id, "due_from": None, "due_to": None},
        )
    ]


def test_patch_and_invalid_transition_are_validated_server_side(client, db, auth_headers):
    account = _make_client(db)
    created = _create_action(client, account.id, auth_headers)

    patched = client.patch(
        f"/api/v1/clients/{account.id}/outcome-actions/{created['id']}",
        headers=auth_headers,
        json={"owner": "Maya", "due_date": "2026-08-15"},
    )
    assert patched.status_code == 200
    assert patched.json()["owner"] == "Maya"
    assert patched.json()["due_date"] == "2026-08-15"

    invalid = client.post(
        f"/api/v1/clients/{account.id}/outcome-actions/{created['id']}/transition",
        headers=auth_headers,
        json={"status": "verified"},
    )
    assert invalid.status_code == 422


def test_archived_client_actions_are_not_accessible(client, db, auth_headers):
    account = _make_client(db, archived=True)

    assert client.get(
        f"/api/v1/clients/{account.id}/outcome-actions", headers=auth_headers
    ).status_code == 404
    assert client.post(
        f"/api/v1/clients/{account.id}/outcome-actions",
        headers=auth_headers,
        json=_payload(),
    ).status_code == 404


def test_review_queue_returns_recommended_actions_for_active_clients(client, db, auth_headers):
    active = _make_client(db)
    archived = _make_client(db, "Archived Dental")
    active_action = _create_action(client, active.id, auth_headers, "content-gap:active")
    _create_action(client, archived.id, auth_headers, "content-gap:archived")
    from app.core.time import utcnow

    archived.archived_at = utcnow()
    db.commit()

    response = client.get("/api/v1/outcome-actions/review-queue", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [row["id"] for row in body["actions"]] == [active_action["id"]]
