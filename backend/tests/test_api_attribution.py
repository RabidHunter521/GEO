"""Attribution API: admin setup, tracked click, inbound webhook."""

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import owner_headers


@pytest.fixture
def client(db):
    from app.core.database import get_db
    from app.main import app

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def account(db):
    from app.models.client import Client

    row = Client(
        name="Klinik Sihat",
        website="https://kliniksihat.example.com",
        industry="Clinic",
        contact_email="hello@example.com",
    )
    db.add(row)
    db.commit()
    return row


def test_admin_routes_require_auth(client, account):
    assert client.get(f"/api/v1/clients/{account.id}/attribution").status_code == 401


def test_setup_overview_and_update(client, account):
    res = client.get(f"/api/v1/clients/{account.id}/attribution", headers=owner_headers())
    assert res.status_code == 200
    body = res.json()
    assert "/wa/" in body["tracked_link_url"]
    assert body["webhook_secret_set"] is False
    assert body["whatsapp_clicks"]["total"] == 0

    res = client.put(
        f"/api/v1/clients/{account.id}/attribution",
        headers=owner_headers(),
        json={"whatsapp_number": "012 345 6789", "tracking_enabled": True},
    )
    assert res.status_code == 422
    res = client.put(
        f"/api/v1/clients/{account.id}/attribution",
        headers=owner_headers(),
        json={"whatsapp_number": "+60 12 345 6789", "tracking_enabled": True},
    )
    assert res.status_code == 200
    assert res.json()["whatsapp_number"] == "60123456789"


def test_tracked_click_returns_whatsapp_redirect(client, account):
    overview = client.get(f"/api/v1/clients/{account.id}/attribution", headers=owner_headers()).json()
    token = overview["tracked_link_url"].rsplit("/", 1)[1]
    res = client.get(
        f"/api/v1/track/whatsapp/{token}",
        params={"fallback": "https://wa.me/60111111111", "ref": "chatgpt.com"},
        headers={"X-Visitor-IP": "203.0.113.5", "X-Visitor-UA": "Mozilla/5.0 Safari"},
    )
    assert res.status_code == 200
    assert res.json() == {"redirect_url": "https://wa.me/60111111111"}

    overview = client.get(f"/api/v1/clients/{account.id}/attribution", headers=owner_headers()).json()
    assert overview["whatsapp_clicks"] == {"total": 1, "ai_attributed": 1, "by_platform": {"ChatGPT": 1}}

    assert client.get("/api/v1/track/whatsapp/unknown").status_code == 404
    res = client.get(f"/api/v1/track/whatsapp/{token}", params={"fallback": "https://evil.example.com"})
    assert res.status_code == 404


def test_webhook_requires_valid_secret_and_is_idempotent(client, account, db):
    from app.models.conversion_event import ConversionEvent

    payload = {"submission_id": "typeform-123", "answer": "ChatGPT", "event_type": "booking",
               "value_minor": 20000, "phone": "ignored extra field"}
    assert client.post("/api/v1/webhooks/heard-about-us", json=payload).status_code == 401
    assert client.post(
        "/api/v1/webhooks/heard-about-us", json=payload, headers={"X-SeenBy-Secret": "sbwh_guess"}
    ).status_code == 401

    secret = client.post(
        f"/api/v1/clients/{account.id}/attribution/webhook-secret", headers=owner_headers()
    ).json()["webhook_secret"]

    res = client.post("/api/v1/webhooks/heard-about-us", json=payload, headers={"X-SeenBy-Secret": secret})
    assert res.status_code == 200
    assert res.json() == {"status": "recorded", "ai_attributed": True}
    res = client.post(
        "/api/v1/webhooks/heard-about-us", json=payload, headers={"Authorization": f"Bearer {secret}"}
    )
    assert res.json() == {"status": "duplicate", "ai_attributed": True}
    assert db.query(ConversionEvent).count() == 1

    # The attributed event reaches the evidence ladder.
    impact = client.get(f"/api/v1/clients/{account.id}/business-impact", headers=owner_headers()).json()
    assert impact[0]["attributed_value_minor"] == 20000
    assert impact[0]["observed_value_minor"] == 0


def test_webhook_rejected_when_tracking_off(client, account):
    secret = client.post(
        f"/api/v1/clients/{account.id}/attribution/webhook-secret", headers=owner_headers()
    ).json()["webhook_secret"]
    client.put(
        f"/api/v1/clients/{account.id}/attribution",
        headers=owner_headers(),
        json={"tracking_enabled": False},
    )
    res = client.post(
        "/api/v1/webhooks/heard-about-us",
        json={"submission_id": "x", "answer": "ChatGPT"},
        headers={"X-SeenBy-Secret": secret},
    )
    assert res.status_code == 403


def test_manual_answer(client, account):
    res = client.post(
        f"/api/v1/clients/{account.id}/attribution/answers",
        headers=owner_headers(),
        json={"answer": "Nampak dalam Gemini"},
    )
    assert res.status_code == 201
    assert res.json()["ai_attributed"] is True
