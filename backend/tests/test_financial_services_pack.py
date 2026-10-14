"""Insurance & consumer finance pack contract: insurers, takaful operators,
agencies, financial advisers, consumer lenders.

A customer finds out an answer was wrong at claim time or at the first
repayment, so licences, representative registration, Shariah status, interest
rates and coverage are the consequential facts.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.industry_packs.financial_services import FINANCIAL_SERVICES_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend|cheapest)\b", re.IGNORECASE)

_FACTS = [ApprovedFact("product", "categories", ["medical card"])]


def _client(**overrides):
    fields = dict(
        name="Acme Takaful", industry="Insurance", buyer_term="takaful operator",
        city="Kuala Lumpur", state=None, country="Malaysia",
        industry_subcategory="takaful_operator",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _texts(client):
    return [
        q["query_text"]
        for q in build_pack_queries(client, [], _FACTS, FINANCIAL_SERVICES_PACK, [])
    ]


def test_is_a_supported_registered_valid_pack():
    assert "financial_services" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("financial_services") is FINANCIAL_SERVICES_PACK
    assert validate_pack(FINANCIAL_SERVICES_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in FINANCIAL_SERVICES_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {
        sub for t in FINANCIAL_SERVICES_PACK.query_templates for sub in t.subcategories
    }
    assert scoped == set(FINANCIAL_SERVICES_PACK.subcategories) - {"other_finance"}


def test_product_questions_are_discovery():
    for q in FINANCIAL_SERVICES_PACK.query_templates:
        used = placeholders_in(q.template)
        if "product" in used and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


def test_every_client_is_asked_whether_it_is_licensed():
    licensed = next(
        q for q in FINANCIAL_SERVICES_PACK.query_templates if q.id == "brand_licensed"
    )
    assert licensed.subcategories == ()


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("regulatory", "licences"),
        ("regulatory", "regulator"),
        ("registration", "representative_licence"),
        ("shariah", "status"),
        ("pricing", "interest_rate"),
        ("product", "coverage"),
    ],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in FINANCIAL_SERVICES_PACK.truth_fields
        if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_licence_claim", "critical"),
        ("wrong_representative_registration", "critical"),
        ("wrong_shariah_status", "critical"),
        ("wrong_interest_rate", "high"),
        ("wrong_coverage", "high"),
        ("wrong_premium", "medium"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in FINANCIAL_SERVICES_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


@pytest.mark.parametrize(
    "subcategory,expected",
    [
        ("insurer", "InsuranceAgency"), ("takaful_operator", "InsuranceAgency"),
        ("insurance_agency", "InsuranceAgency"), ("financial_adviser", "FinancialService"),
        ("consumer_lender", "FinancialService"),
    ],
)
def test_schema_type_per_subcategory(subcategory, expected):
    assert FINANCIAL_SERVICES_PACK.schema_profile.type_for(subcategory) == expected


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in FINANCIAL_SERVICES_PACK.schema_profile.guidance]
    for forbidden in ("interest rates", "premiums", "licence", "shariah", "coverage"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_takaful_operator_gets_product_and_takaful_questions():
    texts = _texts(_client())
    assert "Best medical card in Malaysia" in texts
    assert "Best takaful plan in Malaysia" in texts
    assert "Is Acme Takaful a licensed takaful operator?" in texts
    assert not any("moneylender" in t.lower() for t in texts)
    assert not any("{" in t or "}" in t for t in texts)


def test_consumer_lender_gets_lending_questions():
    texts = _texts(
        _client(
            name="Acme Credit", industry="Finance", buyer_term="moneylender",
            industry_subcategory="consumer_lender",
        )
    )
    assert "Licensed moneylenders in Kuala Lumpur" in texts
    assert "What interest rate does Acme Credit charge?" in texts
    assert not any("takaful" in t.lower() for t in texts)
