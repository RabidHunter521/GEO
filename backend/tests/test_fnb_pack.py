"""F&B pack contract.

The distinguishing risk here is not clinical, it is dietary and religious. A
wrong price annoys; a wrong halal status or a missed allergen can make food
unsafe or unacceptable to eat. Those route above ordinary detail conflicts, and
halal in particular may never be asserted without an approved fact AND a source.
"""
import pytest

from app.industry_packs import registry
from app.industry_packs.base import finding_severity_for, placeholders_in, validate_pack
from app.industry_packs.fnb import FNB_PACK


def _field(fact_type: str, key: str):
    return next(
        (f for f in FNB_PACK.truth_fields if f.fact_type == fact_type and f.key == key), None
    )


def _rule(rule_id: str):
    return next(r for r in FNB_PACK.risk_rules if r.id == rule_id)


def test_pack_is_valid_and_registered():
    assert validate_pack(FNB_PACK) is None
    assert registry.get_pack("fnb") is FNB_PACK
    assert FNB_PACK.version == "1.0.0"


def test_subcategories_match_the_plan():
    assert FNB_PACK.subcategories == (
        "restaurant", "cafe", "bakery", "bar", "catering",
        "food_delivery", "quick_service", "other_fnb",
    )


# --- truth fields -----------------------------------------------------------

@pytest.mark.parametrize(
    "fact_type",
    ["outlet", "menu", "cuisine", "dietary", "pricing", "reservation",
     "delivery", "facility", "occasion", "hours"],
)
def test_pack_covers_every_required_fact_domain(fact_type):
    assert any(f.fact_type == fact_type for f in FNB_PACK.truth_fields)


def test_operating_and_kitchen_hours_are_separate_facts():
    """A kitchen that closes before the venue is the single most common source
    of a wrong "are they open" answer."""
    assert _field("hours", "operating") is not None
    assert _field("hours", "kitchen") is not None


def test_halal_status_and_its_source_are_both_declared():
    assert _field("dietary", "halal_status") is not None
    assert _field("dietary", "halal_certifier") is not None


def test_dietary_and_allergen_facts_are_risk_sensitive():
    """These may never be repeated without a source and an approval."""
    for key in ("halal_status", "halal_certifier", "allergens", "options"):
        field = _field("dietary", key)
        assert field is not None and field.risk_sensitive is True, key


def test_outlet_facts_are_location_scoped():
    for f in FNB_PACK.truth_fields:
        if f.fact_type in ("outlet", "hours"):
            assert f.scope in ("location", "either"), f.key


# --- risk rules -------------------------------------------------------------

@pytest.mark.parametrize(
    "rule_id", ["false_halal_claim", "wrong_allergen_information", "invented_menu_item"],
)
def test_the_food_safety_rules_exist(rule_id):
    assert _rule(rule_id) is not None


@pytest.mark.parametrize(
    "rule_id", ["false_halal_claim", "wrong_allergen_information"],
)
def test_dietary_and_religious_conflicts_are_top_severity(rule_id):
    """Someone may eat something they cannot or must not eat."""
    assert _rule(rule_id).severity == "critical"


def test_an_opening_hours_conflict_is_only_medium():
    """The cross-pack contrast Task 7 asserts: the same hours conflict that is
    medium here is not what a healthcare credential conflict is."""
    assert _rule("wrong_operating_hours").severity == "medium"


def test_price_conflicts_rank_below_dietary_ones():
    assert _rule("wrong_price").severity in ("medium", "low")
    assert _rule("false_halal_claim").severity == "critical"


def test_every_rule_severity_survives_narrowing_to_a_finding():
    for rule in FNB_PACK.risk_rules:
        assert finding_severity_for(rule.severity) in ("high", "medium", "low")


def test_no_rule_promises_a_food_safety_or_certification_verdict():
    """SeenBy observes what AI says; it does not certify anyone's halal status."""
    for rule in FNB_PACK.risk_rules:
        lowered = rule.review_instruction.lower()
        for banned in ("illegal", "non-compliant", "violation", "uncertified", "unsafe to eat"):
            assert banned not in lowered, rule.id


# --- queries ----------------------------------------------------------------

@pytest.mark.parametrize("stage", ["awareness", "consideration", "decision"])
def test_queries_span_the_whole_buyer_journey(stage):
    assert any(q.buyer_stage == stage for q in FNB_PACK.query_templates)


def test_pack_asks_the_questions_diners_actually_ask():
    ids = {q.id for q in FNB_PACK.query_templates}
    for expected in ("dish_discovery", "cuisine_discovery", "occasion", "dietary_requirement",
                     "local_best", "price_check", "delivery_available", "booking",
                     "late_night"):
        assert expected in ids


def test_a_dietary_query_exists_because_it_is_the_highest_stakes_question():
    dietary = [q for q in FNB_PACK.query_templates if "dietary" in q.id or "{dietary}" in q.template]
    assert dietary


def test_every_placeholder_is_fillable():
    fillable = {"brand", "city", "location", "competitor", "industry",
                "cuisine", "dish", "occasion", "dietary", "area"}
    for q in FNB_PACK.query_templates:
        assert placeholders_in(q.template) <= fillable, q.id


def test_no_query_presumes_the_venue_is_the_answer():
    for q in FNB_PACK.query_templates:
        lowered = q.template.lower()
        if "best" in lowered or "recommend" in lowered:
            assert "{brand}" not in q.template, q.id


# --- sources ----------------------------------------------------------------

def test_trusted_sources_include_the_fnb_specific_ones():
    keys = {s.key for s in FNB_PACK.trusted_sources}
    assert "official_website" in keys
    assert "google_business_profile" in keys
    assert "certification_body" in keys
    assert "delivery_platform" in keys


def test_trusted_sources_are_market_neutral():
    for source in FNB_PACK.trusted_sources:
        assert "jakim" not in source.key.lower()
        assert "malaysia" not in source.label.lower()
