"""Education pack contract — K-12 and enrichment.

The risk asymmetry mirrors healthcare's: a wrong fee costs a parent a phone
call, whereas a false accreditation or an invented curriculum can make them
enrol a child for a qualification the school cannot deliver, and they will
not find out for a year.
"""
import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry
from app.industry_packs.base import validate_pack
from app.industry_packs.education import EDUCATION_PACK


def test_education_is_a_supported_key():
    assert "education" in INDUSTRY_PACK_KEYS


def test_the_pack_is_registered_and_valid():
    assert registry.get_pack("education") is EDUCATION_PACK
    assert validate_pack(EDUCATION_PACK) is None


def test_every_supported_key_is_registered():
    assert set(registry.registered_keys()) == set(INDUSTRY_PACK_KEYS)


def test_subcategories():
    assert EDUCATION_PACK.subcategories == (
        "tuition_centre", "enrichment", "kindergarten",
        "international_school", "private_school",
        "language_centre", "driving_school", "other_education",
    )


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("teacher", "name"), ("teacher", "qualification"),
        ("programme", "offered"), ("programme", "curriculum"),
        ("programme", "levels"),
        ("accreditation", "body"), ("accreditation", "registration_number"),
        ("outcomes", "results_published"), ("outcomes", "placements"),
        ("fees", "range"), ("campus", "name"),
        ("admissions", "intake_months"),
    ],
)
def test_required_truth_fields_exist(fact_type, key):
    pairs = {(f.fact_type, f.key) for f in EDUCATION_PACK.truth_fields}
    assert (fact_type, key) in pairs


@pytest.mark.parametrize(
    "fact_type,key",
    [
        ("teacher", "qualification"),
        ("programme", "offered"), ("programme", "curriculum"),
        ("accreditation", "body"), ("accreditation", "registration_number"),
        ("outcomes", "results_published"), ("outcomes", "placements"),
    ],
)
def test_consequential_facts_are_risk_sensitive(fact_type, key):
    """Risk-sensitive facts require a source URL and reviewer approval before
    any surface repeats them."""
    field = next(
        f for f in EDUCATION_PACK.truth_fields
        if (f.fact_type, f.key) == (fact_type, key)
    )
    assert field.risk_sensitive is True


@pytest.mark.parametrize(
    "rule_id,severity",
    [
        ("false_accreditation", "critical"),
        ("false_registration", "critical"),
        ("invented_curriculum", "critical"),
        ("invented_programme", "critical"),
        ("unsupported_results_claim", "critical"),
        ("false_teacher_qualification", "high"),
        ("teacher_not_at_campus", "high"),
        ("wrong_fees", "medium"),
    ],
)
def test_risk_severities_follow_the_harm_asymmetry(rule_id, severity):
    rule = next(r for r in EDUCATION_PACK.risk_rules if r.id == rule_id)
    assert rule.severity == severity


def test_no_risk_instruction_asserts_a_violation():
    """SeenBy routes evidence to a reviewer; it never adjudicates. Education is
    a sector where asserting this would be especially tempting and wrong."""
    banned = (
        "illegal", "unlicensed", "unlawful", "non-compliant", "violation",
        "breach", "compliant",
    )
    for rule in EDUCATION_PACK.risk_rules:
        low = rule.review_instruction.lower()
        assert not any(term in low for term in banned), rule.id


def test_schema_types_are_real_schema_org_types():
    """DrivingSchool is a 404 and LanguageSchool does not exist. validate_pack
    only checks PascalCase, so this is the guard that they never appear."""
    profile = EDUCATION_PACK.schema_profile
    resolved = {profile.type_for(s) for s in EDUCATION_PACK.subcategories}
    assert resolved <= {"EducationalOrganization", "Preschool", "School"}
    assert "DrivingSchool" not in resolved
    assert "LanguageSchool" not in resolved


@pytest.mark.parametrize(
    "subcategory,expected",
    [
        ("kindergarten", "Preschool"),
        ("international_school", "School"),
        ("private_school", "School"),
        ("tuition_centre", "EducationalOrganization"),
        ("driving_school", "EducationalOrganization"),
        ("language_centre", "EducationalOrganization"),
    ],
)
def test_schema_type_per_subcategory(subcategory, expected):
    assert EDUCATION_PACK.schema_profile.type_for(subcategory) == expected


def test_schema_guidance_prefers_course_over_service():
    """The single biggest structured-data win available to this pack, and the
    one no other pack can use."""
    guidance = " ".join(EDUCATION_PACK.schema_profile.guidance)
    assert "Course" in guidance


def test_schema_guidance_forbids_publishing_risk_sensitive_claims():
    """This guidance goes verbatim into the prompt that generates the
    client's live schema.json. Mentioning "accreditation" is not enough — a
    line reading "emit accreditation bodies" would pass a substring check
    while telling the AI to do the opposite of what this pack requires.
    Each risk-sensitive topic must appear inside a sentence that actually
    prohibits emitting it.
    """
    guidance_lines = [line.lower() for line in EDUCATION_PACK.schema_profile.guidance]
    prohibition_markers = ("do not emit", "do not")
    for forbidden in ("accreditation", "teacher", "results", "fee"):
        matching_lines = [line for line in guidance_lines if forbidden in line]
        assert matching_lines, forbidden
        assert any(
            any(marker in line for marker in prohibition_markers)
            for line in matching_lines
        ), f"no prohibition sentence found for {forbidden!r}: {matching_lines}"


def test_every_subcategory_has_scoped_queries_except_other():
    scoped: dict[str, int] = {}
    for template in EDUCATION_PACK.query_templates:
        for sub in template.subcategories:
            scoped[sub] = scoped.get(sub, 0) + 1
    for sub in EDUCATION_PACK.subcategories:
        if sub == "other_education":
            continue
        assert scoped.get(sub, 0) >= 1, f"{sub} has no scoped query"


def test_scoped_queries_are_anchored():
    """Only recommendation/local pay for position extraction, so an unanchored
    yes/no question buys an LLM call it cannot use."""
    from app.industry_packs.base import placeholders_in

    for template in EDUCATION_PACK.query_templates:
        if not template.subcategories:
            continue
        used = placeholders_in(template.template)
        assert used & {"brand", "city", "area", "location"}, template.id


def test_no_query_presumes_the_school_is_the_answer():
    """Templates are buyer questions, not leading questions; a template naming
    the brand inside a "best" or "recommend" question would manufacture the
    very visibility the scan is supposed to measure — asking an AI "is {brand}
    the best school?" is not a measurement."""
    for q in EDUCATION_PACK.query_templates:
        lowered = q.template.lower()
        if "best" in lowered or "recommend" in lowered:
            assert "{brand}" not in q.template, q.id


def test_authority_targets_and_priorities():
    keys = {t.key for t in EDUCATION_PACK.authority_targets}
    assert keys == {"education_register", "schooladvisor", "curriculum_body_directory"}
    assert EDUCATION_PACK.priority_asset_keys == (
        "gbp", "schooladvisor", "education_register", "facebook",
    )


def test_higher_education_directories_are_not_targets():
    """eduadvisor.my and afterschool.my are tertiary-only (verified
    2026-08-08). Wrong buyer for a parent-facing K-12 pack."""
    keys = {t.key for t in EDUCATION_PACK.authority_targets}
    assert "eduadvisor" not in keys
    assert "afterschool_my" not in keys
