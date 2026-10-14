"""Hospitality pack contract: hotels, resorts, homestays, tour operators,
event venues.

A guest finds out an answer was wrong on arrival, so halal status, tourism
licence and cancellation policy are the consequential facts.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.industry_packs.hospitality import HOSPITALITY_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend)\b", re.IGNORECASE)

_FACTS = [
    ApprovedFact("occasion", "suitable_for", ["a family trip"]),
    ApprovedFact("nearby", "attractions", ["Jonker Street"]),
    ApprovedFact("tour", "destinations", ["Langkawi"]),
]


def _client(**overrides):
    fields = dict(
        name="Acme Stay", industry="Hospitality", buyer_term="boutique hotel",
        city="Melaka", state=None, country="Malaysia", industry_subcategory="hotel",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_is_a_supported_registered_valid_pack():
    assert "hospitality" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("hospitality") is HOSPITALITY_PACK
    assert validate_pack(HOSPITALITY_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in HOSPITALITY_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {sub for t in HOSPITALITY_PACK.query_templates for sub in t.subcategories}
    assert scoped == set(HOSPITALITY_PACK.subcategories) - {"other_hospitality"}


def test_fact_anchored_questions_are_discovery():
    for q in HOSPITALITY_PACK.query_templates:
        used = placeholders_in(q.template)
        if used & {"occasion", "attraction", "destination"} and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


@pytest.mark.parametrize(
    "fact_type,key",
    [("dietary", "halal_status"), ("registration", "tourism_licence"), ("policy", "cancellation")],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in HOSPITALITY_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("wrong_halal_status", "critical"),
        ("wrong_tourism_licence", "critical"),
        ("wrong_cancellation_policy", "high"),
        ("wrong_price", "medium"),
        ("wrong_child_policy", "low"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in HOSPITALITY_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


@pytest.mark.parametrize(
    "subcategory,expected",
    [
        ("hotel", "Hotel"), ("resort", "Resort"), ("homestay", "LodgingBusiness"),
        ("tour_operator", "TravelAgency"), ("event_venue", "EventVenue"),
    ],
)
def test_schema_type_per_subcategory(subcategory, expected):
    assert HOSPITALITY_PACK.schema_profile.type_for(subcategory) == expected


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in HOSPITALITY_PACK.schema_profile.guidance]
    for forbidden in ("halal", "licence", "cancellation", "rates"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_hotel_gets_occasion_and_attraction_questions_from_approved_facts():
    texts = [
        q["query_text"]
        for q in build_pack_queries(_client(), [], _FACTS, HOSPITALITY_PACK, [])
    ]
    assert "Where to stay in Melaka for a family trip" in texts
    assert "Best boutique hotel near Jonker Street" in texts
    assert "Family-friendly hotels in Melaka" in texts
    assert not any("{" in t or "}" in t for t in texts)


def test_tour_operator_gets_destination_questions():
    texts = [
        q["query_text"]
        for q in build_pack_queries(
            _client(industry_subcategory="tour_operator", buyer_term="tour operator"),
            [], _FACTS, HOSPITALITY_PACK, [],
        )
    ]
    assert "Best tour packages to Langkawi" in texts
    assert not any("hotel" in t.lower() for t in texts)
