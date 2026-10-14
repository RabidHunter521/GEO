"""Automotive sales pack contract: new and used car dealers, EV showrooms,
motorcycle dealers, car rental. Workshops stay in Local Services.

A buyer pays a deposit on an AI answer, so authorised-dealer status, warranty,
inspection programmes and licences are the consequential facts.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.automotive import AUTOMOTIVE_PACK
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend)\b", re.IGNORECASE)

_FACTS = [
    ApprovedFact("vehicle", "makes", ["Honda"]),
    ApprovedFact("vehicle", "models", ["Honda City"]),
    ApprovedFact("vehicle", "types", ["SUV"]),
]


def _client(**overrides):
    fields = dict(
        name="Acme Auto", industry="Automotive", buyer_term="car dealer",
        city="Shah Alam", state=None, country="Malaysia",
        industry_subcategory="used_car_dealer",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_is_a_supported_registered_valid_pack():
    assert "automotive" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("automotive") is AUTOMOTIVE_PACK
    assert validate_pack(AUTOMOTIVE_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in AUTOMOTIVE_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {sub for t in AUTOMOTIVE_PACK.query_templates for sub in t.subcategories}
    assert scoped == set(AUTOMOTIVE_PACK.subcategories) - {"other_automotive"}


def test_vehicle_questions_are_discovery():
    for q in AUTOMOTIVE_PACK.query_templates:
        used = placeholders_in(q.template)
        if used & {"make", "model", "vehicle_type"} and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("dealer", "authorised_for"), ("warranty", "terms"),
        ("inspection", "programme"), ("licensing", "held"),
    ],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in AUTOMOTIVE_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_authorised_dealer", "critical"),
        ("wrong_warranty", "high"),
        ("wrong_inspection_claim", "high"),
        ("wrong_price", "medium"),
        ("wrong_finance_detail", "low"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in AUTOMOTIVE_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


@pytest.mark.parametrize(
    "subcategory,expected",
    [
        ("new_car_dealer", "AutoDealer"), ("used_car_dealer", "AutoDealer"),
        ("motorcycle_dealer", "MotorcycleDealer"), ("car_rental", "AutoRental"),
    ],
)
def test_schema_type_per_subcategory(subcategory, expected):
    assert AUTOMOTIVE_PACK.schema_profile.type_for(subcategory) == expected


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in AUTOMOTIVE_PACK.schema_profile.guidance]
    for forbidden in ("authorised-dealer", "warranty", "licence", "prices"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_used_car_dealer_gets_make_model_and_type_questions():
    texts = [
        q["query_text"]
        for q in build_pack_queries(
            _client(), [], _FACTS, AUTOMOTIVE_PACK, [SimpleNamespace(name="Rival Cars")],
        )
    ]
    assert "Where to buy a Honda in Shah Alam" in texts
    assert "How much is a Honda City in Malaysia?" in texts
    assert "Where to buy a used SUV in Shah Alam" in texts
    assert not any("{" in t or "}" in t for t in texts)


def test_no_approved_makes_means_no_make_questions():
    template_ids = {
        q["template_id"] for q in build_pack_queries(_client(), [], [], AUTOMOTIVE_PACK, [])
    }
    assert "buy_make_in_city" not in template_ids
    assert "used_reliable" in template_ids
