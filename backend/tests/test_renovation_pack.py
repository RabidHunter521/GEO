"""Renovation & interior design pack contract: contractors, interior designers,
design-and-build, built-in carpentry and landscaping.

Renovation is deposit-first and low-trust, so contractor registration, payment
terms, warranty, insurance and service area are the consequential facts.
"""
import re
from types import SimpleNamespace

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import category_for, placeholders_in, validate_pack
from app.industry_packs.renovation import RENOVATION_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

_SHORTLIST = re.compile(r"\b(best|top|most|recommend|reliable)\b", re.IGNORECASE)

_FACTS = [
    ApprovedFact("work", "types", ["kitchen renovation"]),
    ApprovedFact("work", "property_types", ["condo"]),
    ApprovedFact("design", "styles", ["Japandi"]),
]


def _client(**overrides):
    fields = dict(
        name="Acme Reno", industry="Renovation & Interior Design",
        buyer_term="renovation contractor", city="Petaling Jaya", state="Selangor",
        country="Malaysia", industry_subcategory="general_contractor",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _texts(client, facts=_FACTS):
    return [
        q["query_text"] for q in build_pack_queries(client, [], facts, RENOVATION_PACK, [])
    ]


def test_is_a_supported_registered_valid_pack():
    assert "renovation" in INDUSTRY_PACK_KEYS
    assert registry.get_pack("renovation") is RENOVATION_PACK
    assert validate_pack(RENOVATION_PACK) is None


def test_no_query_presumes_the_brand_is_the_answer():
    for q in RENOVATION_PACK.query_templates:
        if _SHORTLIST.search(q.template) and "{competitor}" not in q.template:
            assert "{brand}" not in q.template, q.id


def test_every_subcategory_has_scoped_queries_except_other():
    scoped = {sub for t in RENOVATION_PACK.query_templates for sub in t.subcategories}
    assert scoped == set(RENOVATION_PACK.subcategories) - {"other_renovation"}


def test_fact_anchored_questions_are_discovery():
    for q in RENOVATION_PACK.query_templates:
        used = placeholders_in(q.template)
        if used & {"work_type", "property_type", "style"} and not used & {"brand", "competitor"}:
            assert category_for(q) in ("recommendation", "local"), q.id


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("registration", "contractor_registration"),
        ("payment", "schedule"),
        ("warranty", "terms"),
        ("insurance", "public_liability"),
        ("coverage", "areas"),
    ],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    field = next(
        f for f in RENOVATION_PACK.truth_fields if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_contractor_registration", "critical"),
        ("wrong_payment_terms", "high"),
        ("wrong_warranty", "high"),
        ("wrong_insurance", "high"),
        ("wrong_service_area", "medium"),
        ("wrong_price", "medium"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in RENOVATION_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


@pytest.mark.parametrize(
    "subcategory,expected",
    [
        ("general_contractor", "GeneralContractor"), ("design_and_build", "GeneralContractor"),
        ("interior_designer", "HomeAndConstructionBusiness"),
        ("carpentry", "HomeAndConstructionBusiness"),
    ],
)
def test_schema_type_per_subcategory(subcategory, expected):
    assert RENOVATION_PACK.schema_profile.type_for(subcategory) == expected


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    lines = [line.lower() for line in RENOVATION_PACK.schema_profile.guidance]
    for forbidden in ("prices", "registration", "warranty", "insurance", "payment"):
        matching = [line for line in lines if forbidden in line]
        assert matching, forbidden
        assert any("do not" in line for line in matching), forbidden


def test_contractor_gets_work_and_property_questions_from_approved_facts():
    texts = _texts(_client())
    assert "Cost of kitchen renovation in Malaysia" in texts
    assert "Best company for kitchen renovation in Petaling Jaya" in texts
    assert "Best contractor for condo renovation in Petaling Jaya" in texts
    assert "Is Acme Reno a registered contractor?" in texts
    assert not any("interior designer" in t.lower() for t in texts)
    assert not any("{" in t or "}" in t for t in texts)


def test_interior_designer_gets_style_questions():
    texts = _texts(_client(industry_subcategory="interior_designer", buyer_term="interior designer"))
    assert "Interior designer for Japandi style in Petaling Jaya" in texts
    assert "Best interior designer in Petaling Jaya" in texts
    assert "Is Acme Reno a registered contractor?" not in texts


def test_property_pack_facts_still_fill_property_type_first():
    # {property_type} gained a renovation source; the property pack's own
    # project.types fact must still win when both exist.
    from app.services.pack_query_service import _fact_values, _Scope

    scope = _Scope(location_id=None, city="KL", region="KL")
    facts = [
        ApprovedFact("project", "types", ["serviced apartment"]),
        ApprovedFact("work", "property_types", ["condo"]),
    ]
    assert _fact_values("property_type", scope, facts) == ["serviced apartment"]
