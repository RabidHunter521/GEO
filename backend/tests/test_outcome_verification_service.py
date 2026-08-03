"""Outcome Action scan-backed verification service."""
from datetime import timedelta


def _make_client(db, name="Acme Dental"):
    from app.models.client import Client

    client = Client(
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
    )
    db.add(client)
    db.commit()
    return client


def _scan(db, client, *, completed=True, completed_at=None):
    from app.core.time import utcnow
    from app.models.scan import Scan

    scan = Scan(
        client_id=client.id,
        status="completed" if completed else "running",
        completed_at=completed_at if completed_at is not None else (utcnow() if completed else None),
    )
    db.add(scan)
    db.commit()
    return scan


def _result(db, scan, *, query_text="best emergency dentist in KL", brand_detected=False):
    from app.models.scan_query_result import ScanQueryResult

    result = ScanQueryResult(
        scan_id=scan.id,
        platform="chatgpt",
        competitor_id=None,
        category="recommendation",
        query_text=query_text,
        response_text="Acme Dental is visible." if brand_detected else "Rival Dental is visible.",
        brand_detected=brand_detected,
    )
    db.add(result)
    db.commit()
    return result


def _waiting_action(db, client, source_result, *, source_ref=None, title="Publish emergency page"):
    from app.core.time import utcnow
    from app.models.outcome_action import OutcomeAction

    action = OutcomeAction(
        client_id=client.id,
        scan_id=source_result.scan_id,
        source_kind="scan_query_result",
        source_ref=source_ref or f"scan_query_result:{source_result.id}",
        action_type="content",
        title=title,
        rationale="Internal rationale must stay private.",
        priority="high",
        confidence="repeated",
        status="waiting_verification",
        destination_url="https://acme.example.com/emergency",
        client_safe_summary="We published a page for emergency dental searches.",
        published_at=utcnow() - timedelta(days=1),
        client_decision="approved",
        client_decided_at=utcnow() - timedelta(days=2),
        approval_evidence_hash="reviewed-hash",
    )
    db.add(action)
    db.commit()
    return action


def test_waiting_action_becomes_verified_when_later_completed_scan_shows_brand(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services.outcome_verification_service import verify_waiting_actions

    client = _make_client(db)
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan, brand_detected=False)
    action = _waiting_action(db, client, source_result)
    after_scan = _scan(db, client, completed_at=action.published_at + timedelta(hours=2))
    _result(db, after_scan, brand_detected=True)

    summary = verify_waiting_actions(after_scan.id, client.id, db)

    db.refresh(action)
    assert summary.verified == 1
    assert summary.no_change == 0
    assert action.status == "verified"
    assert action.verification_result == {
        "basis": "query_presence",
        "before_seen": False,
        "after_seen": True,
        "scan_id": str(after_scan.id),
        "claim": "Observed after publication; causality not established",
    }
    row = db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == f"outcome_action:{action.id}").one()
    assert row.category == "visibility"
    assert row.status == "suggested"
    assert row.description == action.client_safe_summary
    assert action.work_log_entry_id == row.id


def test_waiting_action_becomes_no_change_when_later_scan_still_does_not_show_brand(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services.outcome_verification_service import verify_waiting_actions

    client = _make_client(db)
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan, brand_detected=False)
    action = _waiting_action(db, client, source_result)
    after_scan = _scan(db, client, completed_at=action.published_at + timedelta(hours=2))
    _result(db, after_scan, brand_detected=False)

    summary = verify_waiting_actions(after_scan.id, client.id, db)

    db.refresh(action)
    assert summary.verified == 0
    assert summary.no_change == 1
    assert action.status == "no_change"
    assert action.verification_result["basis"] == "query_presence"
    assert action.verification_result["after_seen"] is False
    assert db.query(WorkLogEntry).count() == 0


def test_missing_comparable_query_leaves_action_waiting_verification(db):
    from app.services.outcome_verification_service import verify_waiting_actions

    client = _make_client(db)
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan)
    action = _waiting_action(db, client, source_result)
    after_scan = _scan(db, client, completed_at=action.published_at + timedelta(hours=2))
    _result(db, after_scan, query_text="best cosmetic dentist in KL", brand_detected=True)

    summary = verify_waiting_actions(after_scan.id, client.id, db)

    db.refresh(action)
    assert summary.skipped_missing_query == 1
    assert action.status == "waiting_verification"
    assert action.verification_result is None


def test_scan_from_another_client_is_rejected_and_ignored(db):
    from app.services.outcome_verification_service import VerificationScanError, verify_waiting_actions

    client = _make_client(db)
    other_client = _make_client(db, "Other Dental")
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan)
    action = _waiting_action(db, client, source_result)
    other_scan = _scan(db, other_client)
    _result(db, other_scan, brand_detected=True)

    try:
        verify_waiting_actions(other_scan.id, client.id, db)
    except VerificationScanError:
        pass
    else:
        raise AssertionError("expected cross-client scan to be rejected")

    db.refresh(action)
    assert action.status == "waiting_verification"


def test_uncompleted_scan_does_not_verify(db):
    from app.services.outcome_verification_service import verify_waiting_actions

    client = _make_client(db)
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan)
    action = _waiting_action(db, client, source_result)
    running_scan = _scan(db, client, completed=False)
    _result(db, running_scan, brand_detected=True)

    summary = verify_waiting_actions(running_scan.id, client.id, db)

    db.refresh(action)
    assert summary.rejected_scan == 1
    assert action.status == "waiting_verification"


def test_verified_action_updates_one_existing_work_log_suggestion(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    from app.services.outcome_verification_service import verify_waiting_actions

    client = _make_client(db)
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan, brand_detected=False)
    action = _waiting_action(db, client, source_result, title="Fallback title")
    existing = work_log_service.suggest(
        client.id,
        "content",
        "Older wording",
        f"outcome_action:{action.id}",
        db,
    )
    after_scan = _scan(db, client, completed_at=action.published_at + timedelta(hours=2))
    _result(db, after_scan, brand_detected=True)

    summary = verify_waiting_actions(after_scan.id, client.id, db)

    rows = db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == f"outcome_action:{action.id}").all()
    db.refresh(action)
    assert summary.work_log_suggested == 1
    assert len(rows) == 1
    assert rows[0].id == existing.id
    assert rows[0].category == "visibility"
    assert rows[0].description == action.client_safe_summary


def test_no_change_action_does_not_create_success_work_log_suggestion(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services.outcome_verification_service import verify_waiting_actions

    client = _make_client(db)
    before_scan = _scan(db, client)
    source_result = _result(db, before_scan, brand_detected=False)
    action = _waiting_action(db, client, source_result)
    after_scan = _scan(db, client, completed_at=action.published_at + timedelta(hours=2))
    _result(db, after_scan, brand_detected=False)

    verify_waiting_actions(after_scan.id, client.id, db)

    assert db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == f"outcome_action:{action.id}").count() == 0
