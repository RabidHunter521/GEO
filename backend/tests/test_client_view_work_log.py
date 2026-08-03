"""Public work-log surface (spec §3.5, §7). Mirrors the fixtures used by the
existing client-view tests — see test_api_client_view.py's `_build_test_client`
for the get_db + rate-limit override pattern this file's `client` fixture reuses.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.main import app
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()


def _client_with_token(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com", industry="Dental clinic",
               contact_email="hello@acme.com", share_token="tok_" + "a" * 40)
    db.add(c)
    db.commit()
    return c


def test_work_log_exposes_only_published_and_whitelisted_fields(client, db):
    from app.core.time import utcnow
    from app.services import work_log_service
    c = _client_with_token(db)
    published = work_log_service.suggest(c.id, "technical", "Verified llms.txt", "r:1", db,
                                         entry_date=utcnow().date())
    work_log_service.update_entry(published, {"status": "published"}, db)
    work_log_service.suggest(c.id, "content", "Still suggested", "r:2", db)
    dismissed = work_log_service.suggest(c.id, "content", "Dismissed", "r:3", db)
    work_log_service.update_entry(dismissed, {"status": "dismissed"}, db)

    r = client.get(f"/api/v1/view/{c.share_token}/work-log")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert set(body[0]) == {"description", "category", "category_label", "entry_date"}
    assert body[0]["description"] == "Verified llms.txt"


def test_work_log_invalid_token_404(client, db):
    r = client.get("/api/v1/view/not-a-real-token/work-log")
    assert r.status_code == 404


def test_work_log_prospect_404(client, db):
    """Prospects get overview + scan only; every other surface returns the
    uniform 404 so a valid token reveals no more than it should."""
    from app.core.time import utcnow
    from app.services import work_log_service
    c = _client_with_token(db)
    c.is_prospect = True
    published = work_log_service.suggest(c.id, "technical", "Verified llms.txt", "r:1", db,
                                         entry_date=utcnow().date())
    work_log_service.update_entry(published, {"status": "published"}, db)
    db.commit()

    r = client.get(f"/api/v1/view/{c.share_token}/work-log")
    assert r.status_code == 404


def test_overview_has_work_log_flag_and_count(client, db):
    from app.core.time import utcnow
    from app.services import work_log_service
    c = _client_with_token(db)
    overview = client.get(f"/api/v1/view/{c.share_token}/overview").json()
    assert overview["has_work_log"] is False
    assert overview["improvements_last_30d"] == 0

    e = work_log_service.suggest(c.id, "technical", "Did a thing", "r:x", db,
                                 entry_date=utcnow().date())
    work_log_service.update_entry(e, {"status": "published"}, db)
    overview2 = client.get(f"/api/v1/view/{c.share_token}/overview").json()
    assert overview2["has_work_log"] is True
    assert overview2["improvements_last_30d"] == 1


# ── deferred minor: the public timeline must be bounded ───────────────────────
# Unauthenticated share-link endpoint; the timeline grows for the life of the
# account, so an uncapped query gets slower forever and is trivially amplified.

def test_public_work_log_is_capped(db):
    from datetime import date
    from app.api.v1.client_view import _MAX_PUBLIC_WORK_LOG_ROWS
    from app.services import work_log_service
    assert _MAX_PUBLIC_WORK_LOG_ROWS > 0

    client = _client_with_token(db)
    for i in range(5):
        e = work_log_service.create_manual(
            client.id, "technical", f"Delivered item {i}", date(2026, 7, 1 + i), db)
        assert e.status == "published"

    capped = work_log_service.published_entries(client.id, db, limit=3)
    assert len(capped) == 3
    # Newest first, so the cap drops the OLDEST history, never recent work.
    assert capped[0].description == "Delivered item 4"

    assert len(work_log_service.published_entries(client.id, db)) == 5


def test_action_plan_exposes_only_client_safe_whitelisted_fields(client, db):
    from datetime import date
    from app.models.outcome_action import OutcomeAction

    c = _client_with_token(db)
    action = OutcomeAction(
        client_id=c.id,
        source_kind="content_gap",
        source_ref="scan_query_result:private",
        title="Publish emergency dental page",
        rationale="Internal rationale must not leak.",
        action_type="content",
        priority="high",
        priority_score=91,
        priority_reasons={"reasons": ["private formula"]},
        confidence="repeated",
        owner="Maya",
        due_date=date(2026, 8, 15),
        status="in_progress",
        destination_url="https://acme.example.com/emergency",
        client_safe_summary="We are preparing a page for emergency dental searches.",
        verification_result={"basis": "query_presence", "scan_id": "private"},
        approval_token_hash="private-token-hash",
    )
    db.add(action)
    db.commit()

    r = client.get(f"/api/v1/view/{c.share_token}/action-plan")

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert set(body[0]) == {
        "title",
        "status_label",
        "due_month",
        "client_safe_summary",
        "destination_url",
    }
    dumped = str(body)
    assert "Internal rationale" not in dumped
    assert "private" not in dumped
    assert "Maya" not in dumped
    assert "priority" not in dumped
    assert body[0]["due_month"] == "August 2026"


def test_action_plan_prospect_404(client, db):
    from app.models.outcome_action import OutcomeAction

    c = _client_with_token(db)
    c.is_prospect = True
    db.add(
        OutcomeAction(
            client_id=c.id,
            source_kind="content_gap",
            source_ref="scan_query_result:private",
            title="Publish emergency dental page",
            rationale="Internal rationale must not leak.",
            action_type="content",
            priority="high",
            confidence="repeated",
            status="in_progress",
            client_safe_summary="We are preparing a page.",
        )
    )
    db.commit()

    r = client.get(f"/api/v1/view/{c.share_token}/action-plan")

    assert r.status_code == 404


def test_completed_work_exposes_verification_claim_without_raw_evidence(client, db):
    from datetime import date
    from app.models.outcome_action import OutcomeAction

    c = _client_with_token(db)
    verified = OutcomeAction(
        client_id=c.id,
        source_kind="content_gap",
        source_ref="scan_query_result:private",
        title="Emergency dental page is live",
        rationale="Internal rationale must not leak.",
        action_type="content",
        priority="high",
        priority_score=91,
        priority_reasons={"reasons": ["private formula"]},
        confidence="repeated",
        owner="Maya",
        due_date=date(2026, 8, 15),
        status="verified",
        destination_url="https://acme.example.com/emergency",
        client_safe_summary="We published a page for emergency dental searches.",
        verification_result={
            "basis": "query_presence",
            "before_seen": False,
            "after_seen": True,
            "scan_id": "private-scan",
            "claim": "Observed after publication; causality not established",
        },
        approval_token_hash="private-token-hash",
    )
    no_change = OutcomeAction(
        client_id=c.id,
        source_kind="content_gap",
        source_ref="scan_query_result:no-change",
        title="No-change action",
        rationale="Internal rationale must not leak.",
        action_type="content",
        priority="medium",
        confidence="repeated",
        status="no_change",
        client_safe_summary="No public success claim here.",
    )
    db.add_all([verified, no_change])
    db.commit()

    r = client.get(f"/api/v1/view/{c.share_token}/completed-work")

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert set(body[0]) == {
        "title",
        "status_label",
        "due_month",
        "completed_month",
        "client_safe_summary",
        "destination_url",
        "verification_claim",
    }
    dumped = str(body)
    assert "private-scan" not in dumped
    assert "before_seen" not in dumped
    assert "after_seen" not in dumped
    assert "Internal rationale" not in dumped
    assert "Maya" not in dumped
    assert "priority" not in dumped
    assert body[0]["status_label"] == "Verified"
    assert body[0]["verification_claim"] == "Observed after publication; causality not established"
