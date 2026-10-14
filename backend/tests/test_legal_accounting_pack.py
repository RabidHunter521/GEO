"""Legal & accounting pack contract: law firms, accounting firms, company
secretaries, bookkeeping and payroll services.

A client hires a professional on trust, so licences, the regulator and
professional qualifications are the consequential facts, and the schema never
publishes results or fees.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.industry_packs.legal_accounting import LEGAL_ACCOUNTING_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend|affordable)\b", re.IGNORECASE)

_FACTS = [ApprovedFact("practice", "areas", ["divorce", "conveyancing"])]


def _client(**overrides):
    fields = dict(
        name="Acme & Partners", industry="Legal & Accounting", buyer_term="law firm",
        city="Kuala Lumpur", state=None, country="Malaysia",
        industry_subcategory="law_firm",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _texts(client):
    return [
        q["query_text"]
        for q in build_pack_queries(client, [], _FACTS, LEGAL_ACCOUNTING_PACK, [])
    ]


def test_is_a_supported_registered_valid_pack():
    assert "legal_accounting" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("legal_accounting") is LEGAL_ACCOUNTING_PACK
    assert validate_pack(LEGAL_ACCOUNTING_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in LEGAL_ACCOUNTING_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {sub for t in LEGAL_ACCOUNTING_PACK.query_templates for sub in t.subcategories}
    assert scoped == set(LEGAL_ACCOUNTING_PACK.subcategories) - {"other_professional"}


def test_practice_area_questions_are_discovery():
    for q in LEGAL_ACCOUNTING_PACK.query_templates:
        used = placeholders_in(q.template)
        if "practice_area" in used and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


@pytest.mark.parametrize(
    "fact_type,key",
    [("regulatory", "licences"), ("regulatory", "regulator"), ("professional", "qualifications")],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in LEGAL_ACCOUNTING_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_licence_claim", "critical"),
        ("wrong_qualification", "high"),
        ("wrong_regulator", "high"),
        ("invented_practice_area", "medium"),
        ("wrong_fees", "medium"),
        ("wrong_consultation_terms", "low"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in LEGAL_ACCOUNTING_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


@pytest.mark.parametrize(
    "subcategory,expected",
    [
        ("law_firm", "LegalService"), ("accounting_firm", "AccountingService"),
        ("bookkeeping", "AccountingService"), ("company_secretary", "ProfessionalService"),
    ],
)
def test_schema_type_per_subcategory(subcategory, expected):
    assert LEGAL_ACCOUNTING_PACK.schema_profile.type_for(subcategory) == expected


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in LEGAL_ACCOUNTING_PACK.schema_profile.guidance]
    for forbidden in ("fees", "licence", "qualification", "success rates"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_law_firm_gets_practice_area_questions_from_approved_facts():
    texts = _texts(_client())
    assert "Best lawyer for divorce in Kuala Lumpur" in texts
    assert "Best firm for conveyancing in Kuala Lumpur" in texts
    assert "How much does divorce cost in Malaysia?" in texts
    assert "Best law firm in Kuala Lumpur" in texts
    assert not any("audit" in t.lower() for t in texts)
    assert not any("{" in t or "}" in t for t in texts)


def test_company_secretary_gets_its_own_questions():
    texts = _texts(_client(industry_subcategory="company_secretary", buyer_term="company secretary"))
    assert "Best company secretary in Kuala Lumpur" in texts
    assert "Is Acme & Partners a licensed company secretary?" in texts
    assert not any("lawyer" in t.lower() for t in texts)
