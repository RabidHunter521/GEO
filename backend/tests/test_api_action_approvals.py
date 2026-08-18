"""Public Outcome Action approval API contract."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.api.v1.action_approvals import _approval_rate_limit
    from app.core.database import get_db
    from app.main import app

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    # The public approval router is rate limited. Override it here, as the
    # client-view API tests do for theirs — otherwise every request in this
    # module makes a real Redis call and blocks on the connect timeout.
    app.dependency_overrides[_approval_rate_limit] = lambda: None
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


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


def _make_action(db, account=None, **overrides):
    from app.models.outcome_action import OutcomeAction

    account = account or _make_client(db)
    values = {
        "client_id": account.id,
        "source_kind": "content_gap",
        "source_ref": f"content-gap:{account.id}",
        "title": "Publish emergency dental page",
        "rationale": "Internal rationale stays private.",
        "action_type": "content",
        "priority": "high",
        "priority_score": 92,
        "priority_reasons": {"reasons": ["private scoring input"]},
        "confidence": "repeated",
        "status": "waiting_client",
        "owner": "Maya",
        "client_safe_summary": "Create an emergency dental page for urgent searches.",
        "destination_url": "https://acmedental.example.com/emergency",
        "verification_result": {"scan_id": "private"},
    }
    values.update(overrides)
    action = OutcomeAction(**values)
    db.add(action)
    db.commit()
    return action


def _approval_token(action, db):
    from app.services.action_approval_service import create_approval_link

    return create_approval_link(action, db)


def test_get_public_approval_returns_whitelisted_fields_without_admin_auth(client, db):
    action = _make_action(db)
    token = _approval_token(action, db)

    response = client.get(f"/api/v1/action-approvals/{token}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "business_name",
        "action_title",
        "client_safe_summary",
        "deliverable_url",
        "destination_url",
        "expires_at",
    }
    assert body["business_name"] == "Acme Dental"
    assert body["action_title"] == "Publish emergency dental page"
    assert body["client_safe_summary"] == "Create an emergency dental page for urgent searches."
    assert body["destination_url"] == "https://acmedental.example.com/emergency"
    assert body["deliverable_url"] is None
    leaked = str(body)
    assert "Internal rationale" not in leaked
    assert "private scoring input" not in leaked
    assert "Maya" not in leaked
    assert str(action.id) not in leaked


@pytest.mark.parametrize("destination_url", ["javascript:alert(1)", "/admin/clients/123", "ftp://example.com/file"])
def test_get_public_approval_omits_unsafe_destination_urls(client, db, destination_url):
    action = _make_action(db, destination_url=destination_url)
    token = _approval_token(action, db)

    response = client.get(f"/api/v1/action-approvals/{token}")

    assert response.status_code == 200
    assert response.json()["destination_url"] is None


def test_post_approve_records_decision_without_admin_auth(client, db):
    action = _make_action(db)
    token = _approval_token(action, db)

    response = client.post(
        f"/api/v1/action-approvals/{token}",
        json={"decision": "approve", "comment": "Approved for launch."},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "recorded", "decision": "approved"}
    db.refresh(action)
    assert action.client_decision == "approved"
    assert action.client_comment == "Approved for launch."
    assert action.client_decided_at is not None
    assert action.approval_evidence_hash
    assert action.approval_token_hash is None


def test_post_request_changes_records_comment_without_approval_evidence(client, db):
    action = _make_action(db)
    token = _approval_token(action, db)

    response = client.post(
        f"/api/v1/action-approvals/{token}",
        json={"decision": "request_changes", "comment": "Please update the offer."},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "recorded", "decision": "request_changes"}
    db.refresh(action)
    assert action.client_decision == "request_changes"
    assert action.client_comment == "Please update the offer."
    assert action.approval_evidence_hash is None
    assert action.approval_token_hash is None


def test_invalid_expired_used_and_archived_tokens_share_uniform_404(client, db):
    from app.core.time import utcnow
    from app.services.action_approval_service import create_approval_link

    expired_action = _make_action(db, source_ref="content-gap:expired")
    expired = create_approval_link(expired_action, db)
    expired_action.approval_expires_at = utcnow() - timedelta(seconds=1)

    used_action = _make_action(db, source_ref="content-gap:used")
    used = create_approval_link(used_action, db)
    used_action.approval_token_hash = None
    used_action.approval_expires_at = None

    archived_account = _make_client(db, "Archived Dental", archived=True)
    archived_action = _make_action(db, account=archived_account, source_ref="content-gap:archived")
    archived = create_approval_link(archived_action, db)
    db.commit()

    for token in ("not-a-token", expired, used, archived):
        get_response = client.get(f"/api/v1/action-approvals/{token}")
        post_response = client.post(
            f"/api/v1/action-approvals/{token}",
            json={"decision": "approve"},
        )
        assert get_response.status_code == 404
        assert post_response.status_code == 404
        assert get_response.json() == post_response.json() == {"detail": "Approval link not found"}


def test_comment_too_long_is_rejected(client, db):
    action = _make_action(db)
    token = _approval_token(action, db)

    response = client.post(
        f"/api/v1/action-approvals/{token}",
        json={"decision": "request_changes", "comment": "x" * 2001},
    )

    assert response.status_code == 422
