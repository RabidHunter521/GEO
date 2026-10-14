"""Property pack contract: developers, agencies, property managers, co-living.

A buyer commits more money on an AI answer here than anywhere else, so tenure,
completion status, registrations and incentives are the critical facts.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.industry_packs.property import PROPERTY_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend)\b", re.IGNORECASE)

_FACTS = [
    ApprovedFact("project", "names", ["Gamuda Gardens"]),
    ApprovedFact("project", "areas", ["Rawang", "Cyberjaya"]),
    ApprovedFact("project", "types", ["condominium"]),
]


def _client(**overrides):
    fields = dict(
        name="Acme Land", industry="Real Estate", buyer_term="property developer",
        city="Kuala Lumpur", state=None, country="Malaysia",
        industry_subcategory="developer",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_is_a_supported_registered_valid_pack():
    assert "property" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("property") is PROPERTY_PACK
    assert validate_pack(PROPERTY_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in PROPERTY_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_no_local_shop_phrasing():
    for q in PROPERTY_PACK.query_templates:
        assert "near me" not in q.template.lower(), q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {sub for t in PROPERTY_PACK.query_templates for sub in t.subcategories}
    assert scoped == set(PROPERTY_PACK.subcategories) - {"other_property"}


def test_district_and_type_questions_are_discovery():
    """Area and property-type questions never name the brand, so a Seen there
    is earned; they must land in a ranked discovery category."""
    for q in PROPERTY_PACK.query_templates:
        used = placeholders_in(q.template)
        if used & {"district", "property_type"} and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("project", "tenure"), ("project", "completion"),
        ("registration", "developer_licence"), ("registration", "agency_registration"),
        ("incentive", "offers"),
    ],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in PROPERTY_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("wrong_tenure", "critical"),
        ("wrong_registration", "critical"),
        ("wrong_completion_status", "high"),
        ("invented_incentive", "high"),
        ("wrong_price", "medium"),
        ("wrong_financing_partner", "low"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in PROPERTY_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


def test_schema_types():
    profile = PROPERTY_PACK.schema_profile
    assert profile.type_for("developer") == "Organization"
    assert profile.type_for("real_estate_agency") == "RealEstateAgent"
    assert profile.type_for("co_living") == "LodgingBusiness"


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in PROPERTY_PACK.schema_profile.guidance]
    for forbidden in ("tenure", "licence", "prices", "incentives"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_developer_gets_area_and_type_questions_from_approved_facts():
    queries = build_pack_queries(
        _client(), [], _FACTS, PROPERTY_PACK, [SimpleNamespace(name="Rival Homes")],
    )
    texts = [q["query_text"] for q in queries]
    assert "Best new condominium projects in Cyberjaya" in texts
    assert "Where can I buy a condominium in Rawang?" in texts
    assert "Upcoming property launches in Rawang" in texts
    assert "Which property developer is the best in Malaysia?" in texts
    assert not any("{" in t or "}" in t for t in texts)


def test_no_approved_area_means_no_area_questions():
    """Nothing is guessed: without approved project areas the client is not
    asked about places it may not sell in."""
    queries = build_pack_queries(_client(), [], [], PROPERTY_PACK, [])
    template_ids = {q["template_id"] for q in queries}
    assert "new_projects_district" not in template_ids
    assert "dev_upcoming_launches" not in template_ids
    assert "brand_overview" in template_ids
