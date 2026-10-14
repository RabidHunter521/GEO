"""Retail & e-commerce pack contract: DTC brands, marketplace sellers,
multi-brand retailers, physical stores.

Shoppers ask about products, so discovery questions come from approved product
facts. Certifications, return policies and warranties are what a shopper
relies on at checkout.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.industry_packs.ecommerce import ECOMMERCE_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend)\b", re.IGNORECASE)

_FACTS = [
    ApprovedFact("product", "categories", ["halal skincare"]),
    ApprovedFact("channel", "marketplaces", ["Shopee"]),
]


def _client(**overrides):
    fields = dict(
        name="Acme Beauty", industry="E-commerce", buyer_term=None,
        city="Kuala Lumpur", state=None, country="Malaysia",
        industry_subcategory="marketplace_seller",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_is_a_supported_registered_valid_pack():
    assert "ecommerce" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("ecommerce") is ECOMMERCE_PACK
    assert validate_pack(ECOMMERCE_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in ECOMMERCE_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {sub for t in ECOMMERCE_PACK.query_templates for sub in t.subcategories}
    assert scoped == set(ECOMMERCE_PACK.subcategories) - {"other_retail"}


def test_product_questions_are_discovery():
    for q in ECOMMERCE_PACK.query_templates:
        used = placeholders_in(q.template)
        if "product" in used and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


def test_legit_question_is_asked_of_every_client():
    template = next(t for t in ECOMMERCE_PACK.query_templates if t.id == "brand_legit")
    assert template.subcategories == ()


@pytest.mark.parametrize(
    "fact_type,key",
    [("product", "certifications"), ("returns", "policy"), ("warranty", "terms")],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in ECOMMERCE_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_certification", "critical"),
        ("wrong_return_policy", "high"),
        ("wrong_warranty", "high"),
        ("wrong_price", "medium"),
        ("wrong_marketplace", "low"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in ECOMMERCE_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


def test_schema_types():
    profile = ECOMMERCE_PACK.schema_profile
    assert profile.type_for("dtc_brand") == "Organization"
    assert profile.type_for("physical_retail") == "Store"


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in ECOMMERCE_PACK.schema_profile.guidance]
    for forbidden in ("halal", "warranty", "return", "prices"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_marketplace_seller_gets_product_and_marketplace_questions():
    queries = build_pack_queries(
        _client(), [], _FACTS, ECOMMERCE_PACK, [SimpleNamespace(name="Rival Beauty")],
    )
    texts = [q["query_text"] for q in queries]
    assert "Best halal skincare brands in Malaysia" in texts
    assert "Best halal skincare shops on Shopee" in texts
    assert "Is Acme Beauty legit?" in texts
    assert "Is Acme Beauty a trusted seller on Shopee?" in texts
    assert not any("{" in t or "}" in t for t in texts)


def test_no_approved_product_means_no_product_questions():
    queries = build_pack_queries(_client(), [], [], ECOMMERCE_PACK, [])
    texts = [q["query_text"] for q in queries]
    assert texts
    assert not any("skincare" in t for t in texts)
