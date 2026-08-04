"""Contracts every industry pack must satisfy, enforced at import time.

Tasks 3-5 add the three real packs. This module tests the MACHINERY with
fixture packs, so a malformed pack fails fast with a named reason instead of
producing subtly wrong queries or risk severities at scan time. The
"exactly three packs are registered" assertion belongs at the end of Task 5,
once all three exist.

The safety invariant here is the important one: a pack may route evidence to a
human reviewer, but it may never assert that something is illegal, unlicensed
or non-compliant. SeenBy is not a regulator and cannot substantiate that claim.
"""
import dataclasses

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs.base import (
    IndustryPack,
    QueryTemplate,
    RiskRule,
    TrustedSourceType,
    TruthFieldDefinition,
    validate_pack,
)
from app.industry_packs import registry


def _field(key="qualification", **kw) -> TruthFieldDefinition:
    return dataclasses.replace(
        TruthFieldDefinition(
            key=key, label="Qualification", value_type="text",
            scope="location", fact_type="practitioner",
        ),
        **kw,
    )


def _template(id="brand_overview", **kw) -> QueryTemplate:
    return dataclasses.replace(
        QueryTemplate(
            id=id,
            template="What is {brand}?",
            buyer_stage="awareness",
            commercial_intent="low",
            location_required=False,
        ),
        **kw,
    )


def _rule(id="credentials", **kw) -> RiskRule:
    return dataclasses.replace(
        RiskRule(
            id=id,
            fact_type="practitioner",
            fact_key="qualification",
            severity="critical",
            review_instruction="Confirm the stated qualification against the approved fact.",
        ),
        **kw,
    )


def _pack(**kw) -> IndustryPack:
    base = IndustryPack(
        key="healthcare",
        version="1.0.0",
        label="Healthcare",
        report_fact_label="Practitioner facts reviewed",
        subcategories=("general_clinic", "dental"),
        truth_fields=(_field(),),
        query_templates=(_template(),),
        risk_rules=(_rule(),),
        trusted_sources=(TrustedSourceType(key="official_website", label="Official website"),),
    )
    return dataclasses.replace(base, **kw)


# --- structural immutability -------------------------------------------------

@pytest.mark.parametrize(
    "obj",
    [_pack(), _field(), _template(), _rule(), TrustedSourceType(key="x", label="X")],
)
def test_pack_definitions_are_frozen(obj):
    """Definitions are returned by reference; a mutable one would let a scan
    edit the pack every later scan reads."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, dataclasses.fields(obj)[0].name, "mutated")


def test_valid_pack_passes_validation():
    assert validate_pack(_pack()) is None


# --- key and version --------------------------------------------------------

def test_pack_key_must_be_a_supported_key():
    with pytest.raises(ValueError, match="unsupported pack key"):
        validate_pack(_pack(key="retail"))


def test_supported_keys_match_the_shared_constant():
    """The schema layer validates against INDUSTRY_PACK_KEYS while the registry
    validates against its own view; if those ever diverge a pack becomes either
    unselectable or unvalidatable."""
    assert registry.SUPPORTED_KEYS == INDUSTRY_PACK_KEYS


@pytest.mark.parametrize("version", ["1", "1.0", "v1.0.0", "", "1.0.0-beta"])
def test_pack_version_must_be_semver(version):
    with pytest.raises(ValueError, match="version"):
        validate_pack(_pack(version=version))


# --- uniqueness -------------------------------------------------------------

def test_truth_field_keys_must_be_unique():
    with pytest.raises(ValueError, match="duplicate truth field"):
        validate_pack(_pack(truth_fields=(_field(), _field())))


def test_the_same_key_under_different_fact_types_is_allowed():
    """practitioner.name and facility.name are different facts."""
    pack = _pack(
        truth_fields=(
            _field(key="name", fact_type="practitioner"),
            _field(key="name", fact_type="facility"),
        ),
        risk_rules=(_rule(fact_type="practitioner", fact_key="name"),),
    )
    assert validate_pack(pack) is None


def test_risk_rule_must_target_a_declared_fact_type():
    with pytest.raises(ValueError, match="which no truth field declares"):
        validate_pack(_pack(risk_rules=(_rule(fact_type="menu", fact_key=None),)))


def test_risk_rule_must_target_a_declared_fact_key():
    """A typo'd fact_key silently never matches, looking like coverage."""
    with pytest.raises(ValueError, match="which no truth field declares"):
        validate_pack(_pack(risk_rules=(_rule(fact_key="qualifcation"),)))


def test_risk_rule_may_match_any_key_of_a_declared_type():
    assert validate_pack(_pack(risk_rules=(_rule(fact_key=None),))) is None


def test_risk_rule_ids_must_be_unique():
    with pytest.raises(ValueError, match="duplicate risk rule"):
        validate_pack(_pack(risk_rules=(_rule(), _rule())))


def test_query_template_ids_must_be_unique():
    with pytest.raises(ValueError, match="duplicate query template"):
        validate_pack(_pack(query_templates=(_template(), _template())))


def test_subcategories_must_be_unique_and_present():
    with pytest.raises(ValueError, match="subcategor"):
        validate_pack(_pack(subcategories=("dental", "dental")))
    with pytest.raises(ValueError, match="subcategor"):
        validate_pack(_pack(subcategories=()))


# --- enumerated values ------------------------------------------------------

def test_truth_field_value_type_must_be_supported():
    with pytest.raises(ValueError, match="value_type"):
        validate_pack(_pack(truth_fields=(_field(value_type="datetime"),)))


def test_truth_field_scope_must_be_supported():
    with pytest.raises(ValueError, match="scope"):
        validate_pack(_pack(truth_fields=(_field(scope="global"),)))


def test_query_buyer_stage_must_be_supported():
    with pytest.raises(ValueError, match="buyer_stage"):
        validate_pack(_pack(query_templates=(_template(buyer_stage="retention"),)))


def test_query_commercial_intent_must_be_supported():
    with pytest.raises(ValueError, match="commercial_intent"):
        validate_pack(_pack(query_templates=(_template(commercial_intent="urgent"),)))


def test_risk_severity_must_be_supported():
    with pytest.raises(ValueError, match="severity"):
        validate_pack(_pack(risk_rules=(_rule(severity="catastrophic"),)))


# --- placeholders -----------------------------------------------------------

def test_query_placeholders_must_come_from_the_allowlist():
    """A typo'd placeholder would reach a model as a literal brace."""
    with pytest.raises(ValueError, match="placeholder"):
        validate_pack(_pack(query_templates=(_template(template="Best {citty} clinic"),)))


def test_location_required_template_must_use_a_location_placeholder():
    with pytest.raises(ValueError, match="location_required"):
        validate_pack(
            _pack(query_templates=(_template(template="What is {brand}?", location_required=True),))
        )


def test_template_using_a_location_placeholder_must_declare_it():
    """Otherwise Task 6 would emit "clinic in {city}" for a client with no location."""
    with pytest.raises(ValueError, match="location_required"):
        validate_pack(
            _pack(
                query_templates=(
                    _template(template="Best clinic in {city}", location_required=False),
                )
            )
        )


# --- the safety invariant ---------------------------------------------------

@pytest.mark.parametrize(
    "instruction",
    [
        "This clinic is operating illegally.",
        "The practitioner is unlicensed.",
        "This is non-compliant with MOH rules.",
        "This breaches advertising regulations.",
        "Confirm the business is legally compliant.",
    ],
)
def test_risk_instructions_may_not_assert_a_violation(instruction):
    """A pack routes evidence to a reviewer; it never adjudicates legality.
    SeenBy cannot substantiate a regulatory claim and must not make one."""
    with pytest.raises(ValueError, match="may not assert"):
        validate_pack(_pack(risk_rules=(_rule(review_instruction=instruction),)))


def test_review_instruction_is_required():
    with pytest.raises(ValueError, match="review_instruction"):
        validate_pack(_pack(risk_rules=(_rule(review_instruction="   "),)))


# --- severity narrowing -----------------------------------------------------
#
# The pack vocabulary has "critical"; the client-facing finding vocabulary does
# not. misinformation_service DROPS a candidate whose severity is outside
# MISINFORMATION_SEVERITIES, logging a warning and moving on — so an unmapped
# pack severity does not raise, it silently deletes the finding. These tests
# exist so that failure mode can never be reached.

def test_every_pack_severity_maps_to_a_real_finding_severity():
    from app.core.constants import MISINFORMATION_SEVERITIES
    from app.industry_packs.base import (
        FINDING_SEVERITY_BY_RISK_SEVERITY, RISK_SEVERITIES, finding_severity_for,
    )

    assert set(FINDING_SEVERITY_BY_RISK_SEVERITY) == set(RISK_SEVERITIES)
    for severity in RISK_SEVERITIES:
        assert finding_severity_for(severity) in MISINFORMATION_SEVERITIES


def test_critical_narrows_to_high_rather_than_vanishing():
    from app.industry_packs.base import finding_severity_for

    assert finding_severity_for("critical") == "high"


def test_unmapped_severity_raises_instead_of_being_dropped():
    from app.industry_packs.base import finding_severity_for

    with pytest.raises(ValueError, match="unmapped pack risk severity"):
        finding_severity_for("catastrophic")


# --- registry lookup --------------------------------------------------------

def test_get_pack_raises_keyerror_for_an_unknown_key():
    with pytest.raises(KeyError):
        registry.get_pack("retail")


def test_registration_rejects_an_invalid_pack():
    with pytest.raises(ValueError):
        registry.register(_pack(version="nope"), _registry={})


def test_registration_rejects_a_duplicate_key():
    store: dict = {}
    registry.register(_pack(), _registry=store)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_pack(), _registry=store)


def test_get_pack_version_returns_none_for_an_unregistered_pack():
    """Used by the client route to stamp a version. Tasks 3-5 register the real
    packs; until then an unregistered key must degrade rather than 500."""
    assert registry.get_pack_version("retail") is None
    assert registry.get_pack_version(None) is None


def test_subcategories_for_returns_empty_for_an_unregistered_pack():
    assert registry.subcategories_for("retail") == ()
