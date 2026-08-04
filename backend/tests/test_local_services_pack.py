"""Local Services pack contract.

The defining risk here is a promise about availability or cover: someone with a
burst pipe at 2am acting on a false "24-hour emergency" answer, or a customer
who believes a tradesperson is insured when the approved facts do not say so.
Those rank above an ordinary price or hours conflict.

This module also closes the registry loop — with all three packs landed,
`registered_keys()` must equal INDUSTRY_PACK_KEYS. Until that assertion exists,
the version-stamping and subcategory-validation paths silently degrade for any
pack whose module has not been imported.
"""
import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import finding_severity_for, placeholders_in, validate_pack
from app.industry_packs.local_services import LOCAL_SERVICES_PACK

PACK = LOCAL_SERVICES_PACK


def _field(fact_type: str, key: str):
    return next(
        (f for f in PACK.truth_fields if f.fact_type == fact_type and f.key == key), None
    )


def _rule(rule_id: str):
    return next(r for r in PACK.risk_rules if r.id == rule_id)


def test_pack_is_valid_and_registered():
    assert validate_pack(PACK) is None
    assert registry.get_pack("local_services") is PACK
    assert PACK.version == "1.0.0"


def test_subcategories_match_the_plan():
    assert PACK.subcategories == (
        "home_maintenance", "automotive", "beauty_wellness", "cleaning",
        "repair", "professional_local", "emergency_service", "other_local_service",
    )


# --- the registry loop, now closable ----------------------------------------

def test_every_supported_pack_key_is_actually_registered():
    """The stamping and subcategory paths degrade gracefully for an unregistered
    pack. This is what turns that degradation back into a hard guarantee."""
    assert set(registry.registered_keys()) == set(INDUSTRY_PACK_KEYS)


def test_every_registered_pack_has_a_distinct_label():
    labels = [p.label for p in registry.all_packs()]
    assert len(labels) == len(set(labels))


def test_all_three_packs_validate():
    for pack in registry.all_packs():
        assert validate_pack(pack) is None


# --- truth fields -----------------------------------------------------------

@pytest.mark.parametrize(
    "fact_type",
    ["service", "coverage", "availability", "licensing", "insurance",
     "pricing", "warranty", "booking"],
)
def test_pack_covers_every_required_fact_domain(fact_type):
    assert any(f.fact_type == fact_type for f in PACK.truth_fields)


@pytest.mark.parametrize(
    "pair",
    [
        ("service", "catalog"),
        ("service", "exclusions"),
        ("coverage", "areas"),
        ("availability", "emergency"),
        ("availability", "same_day"),
        ("availability", "response_time"),
        ("licensing", "held"),
        ("insurance", "public_liability"),
        ("pricing", "model"),
        ("warranty", "terms"),
        ("booking", "channel"),
    ],
)
def test_the_plans_required_fields_are_declared(pair):
    assert _field(*pair) is not None


def test_licensing_insurance_and_emergency_facts_are_risk_sensitive():
    """These are the claims a customer relies on most and can verify least."""
    for pair in [("licensing", "held"), ("insurance", "public_liability"),
                 ("availability", "emergency")]:
        field = _field(*pair)
        assert field is not None and field.risk_sensitive is True, pair


def test_service_exclusions_are_declared_because_absence_is_a_claim():
    """What a trade does NOT do is as load-bearing as what it does; without it,
    an invented service cannot be distinguished from an unlisted one."""
    assert _field("service", "exclusions") is not None


# --- risk rules -------------------------------------------------------------

@pytest.mark.parametrize(
    "rule_id",
    ["false_licensing", "false_insurance", "false_emergency_availability",
     "wrong_service_area", "false_price_guarantee"],
)
def test_the_five_high_stakes_rules_exist(rule_id):
    assert _rule(rule_id) is not None


@pytest.mark.parametrize(
    "rule_id",
    ["false_licensing", "false_insurance", "false_emergency_availability"],
)
def test_availability_and_cover_claims_are_top_severity(rule_id):
    assert _rule(rule_id).severity in ("critical", "high")


def test_false_emergency_availability_is_critical():
    """A 2am callout that never arrives is the worst outcome this pack has."""
    assert _rule("false_emergency_availability").severity == "critical"


def test_every_rule_severity_survives_narrowing_to_a_finding():
    for rule in PACK.risk_rules:
        assert finding_severity_for(rule.severity) in ("high", "medium", "low")


def test_no_rule_asserts_a_licensing_verdict():
    """The one place it would be most tempting — and most wrong — to say
    "unlicensed". SeenBy reports what an AI said, not who holds a licence."""
    for rule in PACK.risk_rules:
        lowered = rule.review_instruction.lower()
        for banned in ("illegal", "unlicensed", "non-compliant", "violation", "uninsured"):
            assert banned not in lowered, rule.id


# --- queries ----------------------------------------------------------------

@pytest.mark.parametrize("stage", ["awareness", "consideration", "decision"])
def test_queries_span_the_whole_buyer_journey(stage):
    assert any(q.buyer_stage == stage for q in PACK.query_templates)


def test_pack_asks_the_questions_a_person_in_trouble_asks():
    ids = {q.id for q in PACK.query_templates}
    for expected in ("problem_solver", "near_me", "emergency", "same_day",
                     "coverage_check", "price_check", "trust_check",
                     "warranty_check", "brand_vs_competitor"):
        assert expected in ids


def test_an_emergency_query_exists_and_is_high_intent():
    emergency = _query("emergency")
    assert emergency.commercial_intent == "high"
    assert emergency.buyer_stage == "decision"


def _query(query_id: str):
    return next(q for q in PACK.query_templates if q.id == query_id)


def test_every_placeholder_is_fillable():
    fillable = {"brand", "city", "location", "competitor", "industry",
                "service", "problem", "area"}
    for q in PACK.query_templates:
        assert placeholders_in(q.template) <= fillable, q.id


def test_no_query_presumes_the_provider_is_the_answer():
    for q in PACK.query_templates:
        lowered = q.template.lower()
        if "best" in lowered or "recommend" in lowered:
            assert "{brand}" not in q.template, q.id


# --- sources ----------------------------------------------------------------

def test_trusted_sources_cover_verification_routes():
    keys = {s.key for s in PACK.trusted_sources}
    assert "official_website" in keys
    assert "licensing_body" in keys
    assert "google_business_profile" in keys
    assert "trade_association" in keys


def test_trusted_sources_are_market_neutral():
    for source in PACK.trusted_sources:
        assert "malaysia" not in source.label.lower()
