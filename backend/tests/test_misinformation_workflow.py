"""Review workflow: suggested → confirmed/dismissed → corrected →
candidate_fixed → verified_fixed, plus the remediation spawn on confirm."""
import pytest

from app.core.time import utcnow
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.remediation_item import RemediationItem
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.misinformation_service import (
    check_candidate_fixed,
    get_findings,
    mark_corrected,
    resolve_finding,
    review_finding,
)

RESPONSE = "Klinik A guarantees full recovery for every patient."


def _setup(db, response_text=RESPONSE, status="suggested"):
    c = Client(name="Klinik A", website="klinik-a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed", completed_at=utcnow())
    db.add(s)
    db.commit()
    r = ScanQueryResult(
        scan_id=s.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?", response_text=response_text,
        brand_detected=True, hallucination_flagged=True,
    )
    db.add(r)
    db.commit()
    f = MisinformationFinding(
        client_id=c.id, scan_query_result_id=r.id,
        quote="guarantees full recovery", category="prohibited_claim",
        rule_key="guaranteed_results", severity="high",
        explanation="Outcome guarantee the clinic cannot make.", status=status,
    )
    db.add(f)
    db.commit()
    return c, s, r, f


def test_confirm_stamps_review_and_spawns_remediation(db):
    client, _, result, finding = _setup(db)

    review_finding(finding.id, "confirm", db)

    db.refresh(finding)
    assert finding.status == "confirmed"
    assert finding.reviewed_at is not None

    item = db.query(RemediationItem).one()
    assert item.item_type == "misinformation"
    assert item.client_id == client.id
    assert item.platform == "chatgpt"
    assert item.label == result.query_text
    assert item.status == "flagged"
    # The tracked detail names the problem, never the raw AI response.
    assert "guarantee" in (item.detail or "").lower()
    assert RESPONSE not in (item.detail or "")


def test_confirm_twice_does_not_duplicate_remediation(db):
    _, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)
    review_finding(finding.id, "confirm", db)
    assert db.query(RemediationItem).count() == 1


def test_dismiss_is_terminal_and_spawns_nothing(db):
    _, _, _, finding = _setup(db)

    review_finding(finding.id, "dismiss", db, note="AI is right, we do offer this")

    db.refresh(finding)
    assert finding.status == "dismissed"
    assert finding.reviewed_at is not None
    assert finding.admin_note == "AI is right, we do offer this"
    assert db.query(RemediationItem).count() == 0


def test_review_rejects_unknown_action_and_missing_finding(db):
    import uuid
    _, _, _, finding = _setup(db)
    with pytest.raises(ValueError):
        review_finding(finding.id, "approve", db)
    assert review_finding(uuid.uuid4(), "confirm", db) is None


def test_mark_corrected_requires_confirmed(db):
    _, _, _, finding = _setup(db)
    # Still "suggested" — correcting an unreviewed finding is not allowed.
    assert mark_corrected(finding.id, db) is None

    review_finding(finding.id, "confirm", db)
    assert mark_corrected(finding.id, db) is not None
    db.refresh(finding)
    assert finding.status == "corrected"


def test_candidate_fixed_only_when_quote_absent_from_new_scan(db):
    client, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)

    # A later scan whose responses still contain the claim — nothing changes.
    repeat = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(repeat)
    db.commit()
    db.add(ScanQueryResult(
        scan_id=repeat.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?",
        response_text="Klinik A guarantees   full recovery for every patient.",
        brand_detected=True,
    ))
    db.commit()

    assert check_candidate_fixed(repeat.id, db) == 0
    db.refresh(finding)
    assert finding.status == "confirmed"

    # A clean scan — the claim is gone, so it becomes a candidate for Faris.
    clean = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(clean)
    db.commit()
    db.add(ScanQueryResult(
        scan_id=clean.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?",
        response_text="Klinik A is a dental clinic in Kuala Lumpur.",
        brand_detected=True,
    ))
    db.commit()

    assert check_candidate_fixed(clean.id, db) == 1
    db.refresh(finding)
    assert finding.status == "candidate_fixed"


def test_candidate_fixed_ignores_scans_with_no_client_rows(db):
    """An empty or failed scan is not evidence that anything was fixed."""
    client, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)

    empty = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(empty)
    db.commit()

    assert check_candidate_fixed(empty.id, db) == 0
    db.refresh(finding)
    assert finding.status == "confirmed"


def test_resolve_only_from_candidate_fixed(db):
    _, _, _, finding = _setup(db, status="confirmed")
    assert resolve_finding(finding.id, db) is None  # admin gates the good news too

    finding.status = "candidate_fixed"
    db.commit()
    assert resolve_finding(finding.id, db) is not None
    db.refresh(finding)
    assert finding.status == "verified_fixed"
    assert finding.resolved_at is not None


def test_get_findings_orders_open_work_first(db):
    client, _, result, first = _setup(db)
    review_finding(first.id, "dismiss", db)
    second = MisinformationFinding(
        client_id=client.id, scan_query_result_id=result.id,
        quote="every patient", category="factual_error", rule_key=None,
        severity="medium", explanation="e",
    )
    db.add(second)
    db.commit()

    rows = get_findings(client.id, db)
    assert [r.status for r in rows] == ["suggested", "dismissed"]


def test_remediation_sync_never_auto_corrects_misinformation_items(db):
    """`sync_remediation_items` only reconciles hallucination/content_gap items,
    so a misinformation item is resolved by the finding workflow alone."""
    from app.services.remediation_service import sync_remediation_items

    client, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)
    item = db.query(RemediationItem).one()

    sync_remediation_items(client.id, db)

    db.refresh(item)
    assert item.status == "flagged"
    assert item.resolved_at is None
