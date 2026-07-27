from app.core.constants import (
    COMPLIANCE_RULES,
    MISINFORMATION_CATEGORIES,
    MISINFORMATION_SEVERITIES,
    MISINFORMATION_STATUSES,
)
from app.core.time import utcnow
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult


def _row(db):
    c = Client(name="Acme Dental", website="acme.com", industry="dentist")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed", completed_at=utcnow())
    db.add(s)
    db.commit()
    r = ScanQueryResult(
        scan_id=s.id, platform="chatgpt", category="brand",
        query_text="Does Acme Dental guarantee results?",
        response_text="Acme Dental guarantees full recovery for every patient.",
        brand_detected=True, hallucination_flagged=True,
    )
    db.add(r)
    db.commit()
    return c, r


def test_finding_roundtrip_defaults_to_suggested(db):
    client, result = _row(db)
    db.add(MisinformationFinding(
        client_id=client.id,
        scan_query_result_id=result.id,
        quote="guarantees full recovery",
        category="prohibited_claim",
        rule_key="guaranteed_results",
        severity="high",
        explanation="AI states an outcome guarantee the clinic cannot make.",
    ))
    db.commit()

    row = db.query(MisinformationFinding).one()
    assert row.status == "suggested"
    assert row.quote == "guarantees full recovery"
    assert row.reviewed_at is None
    assert row.resolved_at is None
    assert row.admin_note is None
    assert row.detected_at is not None


def test_finding_deleted_with_its_source_row(db):
    client, result = _row(db)
    db.add(MisinformationFinding(
        client_id=client.id, scan_query_result_id=result.id,
        quote="guarantees full recovery", category="prohibited_claim",
        rule_key="guaranteed_results", severity="high", explanation="e",
    ))
    db.commit()

    db.delete(result)
    db.commit()

    assert db.query(MisinformationFinding).count() == 0


def test_constants_are_coherent():
    assert MISINFORMATION_CATEGORIES == (
        "wrong_service", "factual_error", "prohibited_claim", "outdated_info",
    )
    assert MISINFORMATION_SEVERITIES == ("high", "medium", "low")
    # candidate_fixed is stored (not just surfaced) so a re-scan suggestion
    # survives between admin sessions.
    assert "candidate_fixed" in MISINFORMATION_STATUSES
    assert MISINFORMATION_STATUSES[0] == "suggested"
    assert "guaranteed_results" in COMPLIANCE_RULES
    assert all(isinstance(v, str) and v for v in COMPLIANCE_RULES.values())
