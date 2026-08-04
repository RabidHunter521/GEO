"""Healthcare pack contract.

The generic validator in test_industry_pack_registry already proves the pack is
structurally sound and that no rule asserts a legal conclusion. These tests pin
the pack's CONTENT: the facts a clinic is judged on, and the fact that the four
highest-stakes conflicts are triaged above an ordinary detail mismatch.
"""
import pytest

from app.industry_packs import registry
from app.industry_packs.base import finding_severity_for, placeholders_in, validate_pack
from app.industry_packs.healthcare import HEALTHCARE_PACK


def _field_keys() -> set[tuple[str, str]]:
    return {(f.fact_type, f.key) for f in HEALTHCARE_PACK.truth_fields}


def _rule(rule_id: str):
    return next(r for r in HEALTHCARE_PACK.risk_rules if r.id == rule_id)


def test_pack_is_valid_and_registered():
    assert validate_pack(HEALTHCARE_PACK) is None
    assert registry.get_pack("healthcare") is HEALTHCARE_PACK
    assert HEALTHCARE_PACK.version == "1.0.0"


def test_subcategories_match_the_plan():
    assert HEALTHCARE_PACK.subcategories == (
        "general_clinic", "dental", "specialist", "aesthetic",
        "physiotherapy", "diagnostics", "pharmacy", "other_healthcare",
    )


# --- truth fields -----------------------------------------------------------

@pytest.mark.parametrize(
    "fact_type",
    ["practitioner", "specialty", "treatment", "accreditation", "facility", "payment"],
)
def test_pack_covers_every_required_fact_domain(fact_type):
    assert any(f.fact_type == fact_type for f in HEALTHCARE_PACK.truth_fields)


@pytest.mark.parametrize(
    "pair",
    [
        ("practitioner", "qualification"),
        ("practitioner", "registration_number"),
        ("practitioner", "specialty"),
        ("treatment", "offered"),
        ("accreditation", "body"),
    ],
)
def test_high_stakes_facts_are_declared(pair):
    assert pair in _field_keys()


def test_credential_and_registration_facts_are_risk_sensitive():
    """These may not be repeated anywhere without a source and an approval."""
    for f in HEALTHCARE_PACK.truth_fields:
        if f.fact_type == "practitioner" and f.key in {"qualification", "registration_number"}:
            assert f.risk_sensitive is True, f"{f.key} must be risk-sensitive"


def test_practitioner_facts_are_location_scoped():
    """A practitioner practises somewhere specific; a brand-scoped credential
    would let one clinic's doctor answer for every branch."""
    for f in HEALTHCARE_PACK.truth_fields:
        if f.fact_type == "practitioner":
            assert f.scope in ("location", "either")


# --- risk rules -------------------------------------------------------------

@pytest.mark.parametrize(
    "rule_id",
    ["false_credentials", "invented_treatment", "practitioner_not_at_location",
     "unsupported_outcome_claim"],
)
def test_the_four_high_stakes_rules_exist(rule_id):
    assert _rule(rule_id) is not None


@pytest.mark.parametrize(
    "rule_id",
    ["false_credentials", "invented_treatment", "practitioner_not_at_location",
     "unsupported_outcome_claim"],
)
def test_high_stakes_rules_outrank_ordinary_detail_conflicts(rule_id):
    """A wrong qualification must not be triaged like a wrong phone number."""
    assert _rule(rule_id).severity in ("critical", "high")


def test_every_rule_severity_survives_narrowing_to_a_finding():
    """Guards the silent-drop path in misinformation_service."""
    for rule in HEALTHCARE_PACK.risk_rules:
        assert finding_severity_for(rule.severity) in ("high", "medium", "low")


def test_no_rule_promises_a_regulatory_verdict():
    """Belt and braces over the validator: instructions describe what to CHECK."""
    for rule in HEALTHCARE_PACK.risk_rules:
        lowered = rule.review_instruction.lower()
        for banned in ("illegal", "unlicensed", "non-compliant", "violation"):
            assert banned not in lowered


# --- queries ----------------------------------------------------------------

@pytest.mark.parametrize(
    "stage", ["awareness", "consideration", "decision"],
)
def test_queries_span_the_whole_buyer_journey(stage):
    assert any(q.buyer_stage == stage for q in HEALTHCARE_PACK.query_templates)


def test_pack_asks_the_commercially_important_questions():
    """Cost, eligibility and comparison are where a clinic actually loses buyers."""
    ids = {q.id for q in HEALTHCARE_PACK.query_templates}
    for expected in ("treatment_cost", "eligibility", "brand_vs_competitor",
                     "practitioner_lookup", "treatment_discovery", "local_best"):
        assert expected in ids


def test_every_placeholder_is_supported_by_a_declared_fact_or_client_field():
    """A placeholder nothing can fill produces a query with a literal brace."""
    fillable = {"brand", "city", "location", "competitor", "industry", "service", "specialty"}
    for q in HEALTHCARE_PACK.query_templates:
        assert placeholders_in(q.template) <= fillable, q.id


def test_high_intent_queries_exist():
    assert any(q.commercial_intent == "high" for q in HEALTHCARE_PACK.query_templates)


def test_no_query_presumes_the_clinic_is_the_answer():
    """Templates are buyer questions, not leading questions; a template naming
    the brand inside a "best" question would manufacture visibility."""
    for q in HEALTHCARE_PACK.query_templates:
        lowered = q.template.lower()
        if "best" in lowered or "recommend" in lowered:
            assert "{brand}" not in q.template, q.id


# --- sources ----------------------------------------------------------------

def test_trusted_sources_cover_the_plan():
    keys = {s.key for s in HEALTHCARE_PACK.trusted_sources}
    assert keys == {
        "official_website", "professional_registry", "accreditation_body",
        "google_business_profile", "recognized_directory", "reviewed_publication",
    }


def test_trusted_sources_are_market_neutral():
    """Naming a specific national body would break the pack outside Malaysia."""
    for source in HEALTHCARE_PACK.trusted_sources:
        assert "malaysia" not in source.label.lower()
        assert "mmc" not in source.key.lower()
