"""Review workflow: suggested → confirmed/dismissed → corrected →
candidate_fixed → verified_fixed, plus the remediation spawn on confirm."""
import pytest

from app.core.time import utcnow
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.remediation_item import RemediationItem
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.truth_fact import TruthFact, TruthFactVersion
from app.services.misinformation_service import (
    check_candidate_fixed,
    get_findings,
    mark_corrected,
    resolve_finding,
    review_finding,
    store_truth_conflict_candidates,
)
from app.services.truth_comparison_service import TruthConflictCandidate

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


def test_truth_conflicts_stay_suggested_until_a_reviewer_confirms_and_sets_severity(db):
    client, _, result, _ = _setup(db)
    fact = TruthFact(client_id=client.id, fact_type="business", fact_key="outcome_policy")
    db.add(fact)
    db.flush()
    version = TruthFactVersion(
        truth_fact_id=fact.id,
        value_json={"value": "No guarantees", "display_value": "No guarantees"},
        status="draft",
    )
    db.add(version)
    db.commit()
    candidate = TruthConflictCandidate(
        answer_quote="guarantees full recovery",
        claim_value="guarantees full recovery",
        truth_fact_id=fact.id,
        truth_fact_version_id=version.id,
        fact_type="business",
        fact_key="outcome_policy",
        approved_value="No guarantees",
        source_url="https://klinik-a.example/policies",
        comparator="text",
    )

    stored = store_truth_conflict_candidates(client.id, result.id, [candidate], db)

    assert stored == 1
    finding = db.query(MisinformationFinding).filter_by(truth_fact_version_id=version.id).one()
    assert finding.status == "suggested"
    assert finding.category == "factual_error"
    assert finding.severity == "low"
    assert finding.truth_fact_id == fact.id
    assert finding.truth_fact_version_id == version.id

    reviewed = review_finding(finding.id, "confirm", db, severity="high")

    assert reviewed is not None
    assert reviewed.status == "confirmed"
    assert reviewed.severity == "high"


def test_confirm_is_refused_once_the_finding_left_review(db):
    """Re-confirming would re-stamp reviewed_at, which re-fires the weekly
    digest protection line and drags a fixed statement back into the PDF's
    open count."""
    _, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)
    first_reviewed_at = finding.reviewed_at

    assert review_finding(finding.id, "confirm", db) is None
    db.refresh(finding)
    assert finding.reviewed_at == first_reviewed_at
    assert db.query(RemediationItem).count() == 1

    for status in ("corrected", "candidate_fixed", "verified_fixed"):
        finding.status = status
        db.commit()
        assert review_finding(finding.id, "confirm", db) is None


def test_a_dismissal_can_be_reversed(db):
    """Dismiss is a judgement call, not a dead end — the admin can change
    their mind, and that first real confirmation should behave normally."""
    _, _, _, finding = _setup(db)
    review_finding(finding.id, "dismiss", db)

    assert review_finding(finding.id, "confirm", db) is not None
    db.refresh(finding)
    assert finding.status == "confirmed"
    assert db.query(RemediationItem).count() == 1


def test_finding_lifecycle_carries_the_spawned_item_with_it(db):
    """sync_remediation_items skips this type, so if the finding workflow
    doesn't move the item, nothing does."""
    _, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)
    item = db.query(RemediationItem).one()
    assert item.status == "flagged"

    mark_corrected(finding.id, db)
    db.refresh(item)
    assert item.status == "in_progress"

    finding.status = "candidate_fixed"
    db.commit()
    resolve_finding(finding.id, db)
    db.refresh(item)
    assert item.status == "corrected"
    assert item.resolved_at is not None


def test_spawn_survives_a_retired_compliance_rule(db):
    """COMPLIANCE_RULES is Faris-maintained; a key can be retired while a
    finding citing it is still queued. That must not 500 the confirm."""
    _, _, _, finding = _setup(db)
    finding.rule_key = "rule_that_was_removed_last_month"
    db.commit()

    assert review_finding(finding.id, "confirm", db) is not None
    item = db.query(RemediationItem).one()
    assert item.detail == "Claim that creates advertising risk"


def test_two_problems_in_one_answer_keep_both_details(db):
    client, _, result, first = _setup(db)
    second = MisinformationFinding(
        client_id=client.id, scan_query_result_id=result.id,
        quote="every patient", category="wrong_service", rule_key=None,
        severity="medium", explanation="They don't offer this.",
    )
    db.add(second)
    db.commit()

    review_finding(first.id, "confirm", db)
    review_finding(second.id, "confirm", db)

    item = db.query(RemediationItem).one()  # dedupe key can't tell them apart
    assert "advertising risk" in item.detail
    assert "does not offer" in item.detail


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


def test_no_flip_when_the_findings_platform_was_not_rechecked(db):
    """Per-platform scan failures are expected (CLAUDE.md §5). A platform that
    errored contributes no rows — "we didn't ask" is not "it's gone"."""
    client, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)

    # ChatGPT (the finding's platform) failed; the others answered cleanly.
    partial = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(partial)
    db.commit()
    for platform in ("perplexity", "gemini", "claude"):
        db.add(ScanQueryResult(
            scan_id=partial.id, platform=platform, category="brand",
            query_text="Is Klinik A any good?",
            response_text="Klinik A is a dental clinic in Kuala Lumpur.",
            brand_detected=True,
        ))
    db.commit()

    assert check_candidate_fixed(partial.id, db) == 0
    db.refresh(finding)
    assert finding.status == "confirmed"


def test_candidate_fixed_reverts_when_the_statement_comes_back(db):
    """AI answers vary between runs. Without a way back, a one-scan absence
    would leave "Confirm fixed" on offer forever for a live statement."""
    client, _, _, finding = _setup(db)
    review_finding(finding.id, "confirm", db)
    finding.status = "candidate_fixed"
    db.commit()

    regression = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(regression)
    db.commit()
    db.add(ScanQueryResult(
        scan_id=regression.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?", response_text=RESPONSE, brand_detected=True,
    ))
    db.commit()

    assert check_candidate_fixed(regression.id, db) == 1
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
