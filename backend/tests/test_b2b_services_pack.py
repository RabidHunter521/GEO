"""B2B and online services pack contract.

Built because the legacy templates asked a nationwide payment gateway local-shop
questions ("Best payment gateway near me in Kuala Lumpur", "Signs I need a
payment gateway"). Buyers here shop by country, fees and integrations.
"""
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.b2b_services import B2B_SERVICES_PACK
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.services.pack_query_service import ApprovedFact, build_pack_queries


def _client(**overrides):
    fields = dict(
        name="Curlec", industry="payment gateway", city="Kuala Lumpur",
        state="Wilayah Persekutuan", country="Malaysia",
        industry_subcategory="payment_gateway",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


_FACTS = [
    ApprovedFact("service", "catalog", ["online payment gateway"]),
    ApprovedFact("integration", "platforms", ["Shopify", "WooCommerce"]),
]


def test_is_a_supported_registered_valid_pack():
    assert "b2b_services" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("b2b_services") is B2B_SERVICES_PACK
    assert validate_pack(B2B_SERVICES_PACK) is None
    assert set(registry.registered_keys()) == set(INDUSTRY_PACK_KEYS)


def test_no_local_shop_phrasing():
    for q in B2B_SERVICES_PACK.query_templates:
        lowered = q.template.lower()
        assert "near me" not in lowered, q.id
        assert "signs i need" not in lowered, q.id


def test_no_query_presumes_the_brand_is_the_answer():
    """A "best"/"which"/"most" question naming the brand would manufacture the
    visibility the scan is supposed to measure."""
    import re

    shortlist = re.compile(r"\b(best|top|most|lowest|recommend)\b", re.IGNORECASE)
    for q in B2B_SERVICES_PACK.query_templates:
        if not shortlist.search(q.template) or "{competitor}" in q.template:
            continue  # head-to-head comparison names both by design
        assert "{brand}" not in q.template, q.id


def test_discovery_questions_are_pinned_to_the_country():
    """Buyer-neutral questions must be ranked categories (recommendation or
    local) so they count toward discovery visibility."""
    for q in B2B_SERVICES_PACK.query_templates:
        used = placeholders_in(q.template)
        if used & {"brand", "competitor"}:
            continue
        assert category_for(q) in ("recommendation", "local"), q.id
        assert used & {"country", "city"}, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped: dict[str, int] = {}
    for template in B2B_SERVICES_PACK.query_templates:
        for sub in template.subcategories:
            scoped[sub] = scoped.get(sub, 0) + 1
    for sub in B2B_SERVICES_PACK.subcategories:
        if sub == "other_b2b":
            continue
        assert scoped.get(sub, 0) >= 1, f"{sub} has no scoped query"


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("regulatory", "licences"), ("regulatory", "regulator"),
        ("security", "certifications"), ("payment", "methods_supported"),
        ("payment", "settlement_time"),
    ],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in B2B_SERVICES_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_licence_claim", "critical"),
        ("false_security_certification", "critical"),
        ("wrong_payment_methods", "high"),
        ("invented_service", "high"),
        ("wrong_pricing", "medium"),
        ("wrong_parent_company", "low"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in B2B_SERVICES_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in B2B_SERVICES_PACK.schema_profile.guidance]
    for forbidden in ("licence", "certification", "fees"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_schema_types():
    profile = B2B_SERVICES_PACK.schema_profile
    assert profile.type_for("payment_gateway") == "Organization"
    assert profile.type_for("professional_services") == "ProfessionalService"


def test_payment_gateway_client_gets_country_pinned_questions():
    queries = build_pack_queries(
        _client(), [], _FACTS, B2B_SERVICES_PACK,
        [SimpleNamespace(name="Billplz"), SimpleNamespace(name="iPay88")],
    )
    texts = [q["query_text"] for q in queries]
    assert "Best payment gateway for an online store in Malaysia" in texts
    assert "Best payment gateway for Shopify in Malaysia" in texts
    assert "Which payment gateway in Malaysia has the lowest fees?" in texts
    assert "Curlec vs Billplz: which is better for a business in Malaysia?" in texts
    assert not any("{" in t or "}" in t for t in texts)
    assert not any("near me" in t.lower() for t in texts)
    discovery = [q for q in queries if q["category"] in ("recommendation", "local")]
    assert len(discovery) >= 10


def test_client_without_a_country_is_not_asked_country_questions():
    """Nothing is guessed: no country, no "...in {country}" questions."""
    queries = build_pack_queries(
        _client(country=None), [], _FACTS, B2B_SERVICES_PACK, [],
    )
    texts = [q["query_text"] for q in queries]
    assert texts, "brand questions and the city question still run"
    assert not any("Malaysia" in t for t in texts)
    assert "Top payment gateway companies in Kuala Lumpur" in texts


def test_other_subcategories_do_not_get_payment_questions():
    queries = build_pack_queries(
        _client(industry="accounting firm", industry_subcategory="professional_services"),
        [], _FACTS, B2B_SERVICES_PACK, [],
    )
    template_ids = {q["template_id"] for q in queries}
    assert not any(t.startswith("pg_") for t in template_ids)
    assert "ps_for_smes" in template_ids
