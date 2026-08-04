"""Pack-specific triage of Truth Vault conflicts.

The point of the whole pack system in one place: the SAME kind of conflict means
different things in different industries. A wrong opening time is an annoyance
for a restaurant and an annoyance for a clinic, but a wrong practitioner
credential is not remotely the same thing as a wrong cuisine label.

What never varies is the OUTPUT KIND. Every result is a reviewer candidate.
Nothing here concludes that anyone broke a rule.
"""
import pytest

from app.core.constants import MISINFORMATION_SEVERITIES
from app.industry_packs.fnb import FNB_PACK
from app.industry_packs.healthcare import HEALTHCARE_PACK
from app.industry_packs.local_services import LOCAL_SERVICES_PACK
from app.services.pack_risk_service import evaluate_pack_risk


def _conflict(fact_type, fact_key):
    from app.services.truth_comparison_service import TruthConflictCandidate
    import uuid

    return TruthConflictCandidate(
        answer_quote="an AI said something",
        claim_value="claimed",
        truth_fact_id=uuid.uuid4(),
        truth_fact_version_id=uuid.uuid4(),
        fact_type=fact_type,
        fact_key=fact_key,
        approved_value="approved",
        source_url=None,
        comparator="text",
    )


# --- the cross-pack contrast the plan asks for ------------------------------

def test_the_same_hours_conflict_is_medium_for_a_restaurant():
    result = evaluate_pack_risk(FNB_PACK, _conflict("hours", "operating"))
    assert result.severity == "medium"


def test_false_practitioner_credentials_are_critical_for_healthcare():
    result = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("practitioner", "qualification"))
    assert result.severity == "critical"


def test_false_emergency_availability_is_critical_for_local_services():
    result = evaluate_pack_risk(LOCAL_SERVICES_PACK, _conflict("availability", "emergency"))
    assert result.severity == "critical"


def test_the_three_packs_triage_their_own_worst_case_above_an_hours_conflict():
    """The whole justification for per-pack routing, asserted directly."""
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    hours = rank[evaluate_pack_risk(FNB_PACK, _conflict("hours", "operating")).severity]
    for pack, conflict in [
        (HEALTHCARE_PACK, _conflict("practitioner", "qualification")),
        (FNB_PACK, _conflict("dietary", "halal_status")),
        (LOCAL_SERVICES_PACK, _conflict("availability", "emergency")),
    ]:
        assert rank[evaluate_pack_risk(pack, conflict).severity] < hours


# --- matching -----------------------------------------------------------

def test_an_exact_fact_key_rule_wins_over_a_wildcard():
    """healthcare declares both treatment.offered (critical) and a
    treatment/any wildcard; the specific rule must win."""
    exact = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("treatment", "offered"))
    assert exact.rule_id == "invented_treatment"
    assert exact.severity == "critical"


def test_a_wildcard_rule_matches_any_key_of_its_type():
    result = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("treatment", "price_range"))
    assert result.rule_id == "unsupported_outcome_claim"


def test_an_unmatched_conflict_falls_back_to_medium():
    result = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("nonexistent", "whatever"))
    assert result.severity == "medium"
    assert result.rule_id is None


def test_no_pack_keeps_todays_low_default():
    """Unpacked clients must not have their triage silently changed."""
    result = evaluate_pack_risk(None, _conflict("hours", "operating"))
    assert result.severity == "low"
    assert result.rule_id is None
    assert result.pack_key is None


# --- narrowing to the storable vocabulary -----------------------------------

def test_finding_severity_is_always_storable():
    """critical does not exist in MISINFORMATION_SEVERITIES; a finding created
    with it would be silently discarded by misinformation_service."""
    for pack in (HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK):
        for rule in pack.risk_rules:
            result = evaluate_pack_risk(pack, _conflict(rule.fact_type, rule.fact_key or "any"))
            assert result.finding_severity in MISINFORMATION_SEVERITIES


def test_critical_is_preserved_in_provenance_even_though_it_narrows():
    """Triage ordering must survive the narrowing, or "critical" is meaningless."""
    result = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("practitioner", "qualification"))
    assert result.severity == "critical"
    assert result.finding_severity == "high"
    assert "critical" in result.provenance


# --- auditability -----------------------------------------------------------

def test_result_carries_rule_pack_and_version():
    result = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("practitioner", "qualification"))
    assert result.rule_id == "false_credentials"
    assert result.pack_key == "healthcare"
    assert result.pack_version == HEALTHCARE_PACK.version


def test_provenance_fits_the_storage_column():
    """rule_key is String(64); a longer value would be truncated or rejected."""
    for pack in (HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK):
        for rule in pack.risk_rules:
            result = evaluate_pack_risk(pack, _conflict(rule.fact_type, rule.fact_key or "any"))
            assert len(result.provenance) <= 64, result.provenance


def test_provenance_identifies_the_pack_version_and_rule():
    result = evaluate_pack_risk(LOCAL_SERVICES_PACK, _conflict("licensing", "held"))
    assert "local_services" in result.provenance
    assert LOCAL_SERVICES_PACK.version in result.provenance
    assert "false_licensing" in result.provenance


# --- the invariant that outranks all of the above ---------------------------

@pytest.mark.parametrize("pack", [HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK])
def test_every_result_is_a_review_candidate_never_a_verdict(pack):
    for rule in pack.risk_rules:
        result = evaluate_pack_risk(pack, _conflict(rule.fact_type, rule.fact_key or "any"))
        assert result.needs_review is True
        lowered = result.review_instruction.lower()
        for banned in ("illegal", "unlicensed", "non-compliant", "violation"):
            assert banned not in lowered, rule.id


def test_the_fallback_instruction_is_also_a_review_prompt():
    result = evaluate_pack_risk(HEALTHCARE_PACK, _conflict("nothing", "here"))
    assert result.needs_review is True
    assert result.review_instruction.strip()


# --- persistence: where the triage actually lands ---------------------------

def _scan_setup(db, industry_pack=None):
    """A client with one completed scan, one query row and one approved fact."""
    from datetime import datetime

    from app.models.client import Client
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.truth_fact import TruthFact, TruthFactVersion

    client = Client(
        name="Klinik", website="https://k.my", industry="dental clinic",
        industry_pack=industry_pack,
    )
    db.add(client)
    db.flush()
    scan = Scan(client_id=client.id, status="completed", completed_at=datetime(2026, 1, 2))
    db.add(scan)
    db.flush()
    row = ScanQueryResult(
        scan_id=scan.id, platform="chatgpt", category="brand",
        query_text="q", response_text="Dr Lee holds a PhD in dentistry.",
        brand_detected=True,
    )
    db.add(row)
    fact = TruthFact(
        client_id=client.id, fact_type="practitioner", fact_key="qualification"
    )
    db.add(fact)
    db.flush()
    version = TruthFactVersion(
        truth_fact_id=fact.id, value_json="BDS", status="approved",
        effective_from=datetime(2020, 1, 1), approved_at=datetime(2020, 1, 1),
        approved_by="admin",
    )
    db.add(version)
    db.flush()
    return client, row, fact, version


def _candidate(fact, version, quote="Dr Lee holds a PhD in dentistry."):
    from app.services.truth_comparison_service import TruthConflictCandidate

    return TruthConflictCandidate(
        answer_quote=quote,
        claim_value="PhD",
        truth_fact_id=fact.id,
        truth_fact_version_id=version.id,
        fact_type=fact.fact_type,
        fact_key=fact.fact_key,
        approved_value="BDS",
        source_url=None,
        comparator="text",
    )


def test_a_packed_client_stores_the_pack_severity_and_provenance(db):
    from app.models.misinformation_finding import MisinformationFinding
    from app.services.misinformation_service import store_truth_conflict_candidates

    client, row, fact, version = _scan_setup(db, industry_pack="healthcare")
    db.commit()

    stored = store_truth_conflict_candidates(
        client.id, row.id, [_candidate(fact, version)], db
    )
    assert stored == 1

    finding = db.query(MisinformationFinding).one()
    # critical narrows to high for storage, and the narrowing is recorded
    assert finding.severity == "high"
    assert "healthcare" in finding.rule_key
    assert "false_credentials" in finding.rule_key
    assert "critical" in finding.rule_key


def test_an_unpacked_client_keeps_the_pre_phase_four_default(db):
    """Adding packs must not retroactively re-triage existing clients."""
    from app.models.misinformation_finding import MisinformationFinding
    from app.services.misinformation_service import store_truth_conflict_candidates

    client, row, fact, version = _scan_setup(db, industry_pack=None)
    db.commit()

    store_truth_conflict_candidates(client.id, row.id, [_candidate(fact, version)], db)

    finding = db.query(MisinformationFinding).one()
    assert finding.severity == "low"
    assert finding.rule_key is None


def test_a_rescan_never_overwrites_an_admin_adjusted_severity(db):
    """The admin's judgement outranks the pack's default, permanently."""
    from app.models.misinformation_finding import MisinformationFinding
    from app.services.misinformation_service import store_truth_conflict_candidates

    client, row, fact, version = _scan_setup(db, industry_pack="healthcare")
    db.commit()
    store_truth_conflict_candidates(client.id, row.id, [_candidate(fact, version)], db)

    finding = db.query(MisinformationFinding).one()
    finding.severity = "low"          # admin downgraded it during review
    finding.admin_note = "known, agreed with clinic"
    db.commit()

    # the same conflict is observed again
    stored = store_truth_conflict_candidates(
        client.id, row.id, [_candidate(fact, version)], db
    )

    assert stored == 0, "a duplicate finding was created"
    refreshed = db.query(MisinformationFinding).one()
    assert refreshed.severity == "low"
    assert refreshed.admin_note == "known, agreed with clinic"


def test_the_stored_explanation_tells_the_reviewer_what_to_check(db):
    from app.models.misinformation_finding import MisinformationFinding
    from app.services.misinformation_service import store_truth_conflict_candidates

    client, row, fact, version = _scan_setup(db, industry_pack="healthcare")
    db.commit()
    store_truth_conflict_candidates(client.id, row.id, [_candidate(fact, version)], db)

    explanation = db.query(MisinformationFinding).one().explanation.lower()
    assert "check" in explanation or "confirm" in explanation
    for banned in ("illegal", "unlicensed", "non-compliant"):
        assert banned not in explanation
