# Education Intelligence Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth industry intelligence pack covering K-12 and enrichment education, specialising scan queries, accuracy risk routing, published schema.org markup and authority targets without forking the horizontal platform.

**Architecture:** The pack is a frozen `IndustryPack` dataclass registered at import time, exactly like the three that exist. Two changes live OUTSIDE the pack file and are what make it actually work: `ALLOWED_PLACEHOLDERS` gains `subject`/`level`, and `_FACT_SOURCES` learns to fill them from `programme.*` facts. A hand-written frontend mirror entry keeps the admin form in sync.

**Tech Stack:** Python 3.14, SQLAlchemy, pytest, Next.js 15, TypeScript, vitest

**Spec:** `docs/superpowers/specs/2026-08-08-education-pack-design.md`

## Global Constraints

- Run backend commands through the project venv: `backend/.venv/Scripts/python.exe`. System Python has a broken WeasyPrint and will fail unrelated PDF tests.
- Use `rtk` for git and test commands (see CLAUDE.md).
- No schema change and NO Alembic migration. `INDUSTRY_PACK_KEYS` is a plain tuple with no Postgres enum, by design.
- No score weight change, so `SCORE_VERSION` is NOT bumped.
- `MAX_PACK_QUERIES_PER_SCAN` stays 28.
- Pack risk `review_instruction` text may never assert a legal or regulatory conclusion. `validate_pack` rejects: illegal, illegally, unlicensed, unlawful, non-compliant, noncompliant, violation, violates, breach, breaches, prosecut, compliant.
- Client-facing language rules (CLAUDE.md §2) apply: never "cited", "mentioned", "citation rate", "ranking position", "visibility gap", "first mentioned".
- Every scoped query template must be anchored to `{brand}` or a location placeholder (`{city}`/`{area}`/`{location}`). Only the `recommendation` and `local` categories pay for position extraction, so an unanchored yes/no question buys an LLM call it cannot use.
- schema.org types must actually exist. `DrivingSchool` (404) and `LanguageSchool` (does not exist) were verified absent. `validate_pack` only checks PascalCase format, not existence.
- Branch: `feat/education-pack`. Create it before Task 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/core/constants.py` | add `"education"` to `INDUSTRY_PACK_KEYS` |
| `backend/app/industry_packs/base.py` | add `subject`, `level` to `ALLOWED_PLACEHOLDERS` |
| `backend/app/industry_packs/education.py` | the pack definition (new, ~330 lines) |
| `backend/app/industry_packs/__init__.py` | import so the pack self-registers |
| `backend/app/services/pack_query_service.py` | teach `_FACT_SOURCES` the new placeholders |
| `backend/tests/test_education_pack.py` | pack contract tests (new) |
| `backend/tests/test_local_services_pack.py` | update stale "all three packs" wording |
| `frontend/src/lib/industry-packs.ts` | admin-form mirror entry |

---

### Task 1: Land the pack, its key, and the new placeholders

These cannot be split. `test_every_supported_pack_key_is_actually_registered`
in `tests/test_local_services_pack.py:51` asserts
`set(registered_keys()) == set(INDUSTRY_PACK_KEYS)`, so adding the key without
the module — or the module without the key — leaves the suite red. The
placeholders must land in the same task because `validate_pack` rejects the
pack's templates at import without them.

**Files:**
- Modify: `backend/app/core/constants.py:340`
- Modify: `backend/app/industry_packs/base.py` (`ALLOWED_PLACEHOLDERS`)
- Create: `backend/app/industry_packs/education.py`
- Modify: `backend/app/industry_packs/__init__.py`
- Create: `backend/tests/test_education_pack.py`

**Interfaces:**
- Produces: `EDUCATION_PACK` (an `IndustryPack`), registered under key `"education"`, version `"1.0.0"`.
- Produces: truth field `fact_type`/`key` pairs consumed by Task 2 and Task 4: `programme.offered`, `programme.levels`, `programme.curriculum`, `teacher.qualification`, `accreditation.body`, `accreditation.registration_number`, `outcomes.results_published`, `outcomes.placements`, `fees.range`, `campus.name`, `admissions.intake_months`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_education_pack.py`:

```python
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
    guidance = " ".join(EDUCATION_PACK.schema_profile.guidance).lower()
    for forbidden in ("accreditation", "teacher", "results", "fee"):
        assert forbidden in guidance, forbidden


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
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_education_pack.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'app.industry_packs.education'`.

- [ ] **Step 3: Add the pack key**

In `backend/app/core/constants.py`, change line 340:

```python
INDUSTRY_PACK_KEYS: Final = ("healthcare", "fnb", "local_services", "education")
```

- [ ] **Step 4: Add the new placeholders**

In `backend/app/industry_packs/base.py`, replace the `ALLOWED_PLACEHOLDERS` block:

```python
ALLOWED_PLACEHOLDERS = frozenset({
    "brand", "service", "specialty", "city", "location", "area",
    "competitor", "industry", "cuisine", "dish", "occasion", "dietary", "problem",
    # Education. Deliberately new names rather than overloading {service} and
    # {specialty}: the templates then read correctly, and an existing pack has
    # no programme.* facts so nothing about it changes.
    "subject", "level",
})
```

- [ ] **Step 5: Write the pack**

Create `backend/app/industry_packs/education.py`:

```python
"""Education intelligence pack — K-12 and enrichment.

Covers tuition centres, enrichment providers, kindergartens, private and
international schools, language centres and driving schools. Higher education
is deliberately OUT: programme-level accreditation is a second risk vocabulary
and the buyer is an adult learner rather than a parent.

The risk asymmetry is close to healthcare's. A wrong fee costs a parent a
phone call. A false accreditation, an invented curriculum, or a fabricated
results claim can make a parent enrol a child for a qualification the school
cannot deliver, and they will not find out for a year. The risk rules encode
exactly that.

Every instruction tells a reviewer what to CHECK. None asserts that anything
is improper — SeenBy observes what AI systems say and is not in a position to
adjudicate a regulatory question. The base validator enforces this.
"""
from app.industry_packs import registry
from app.industry_packs.base import (
    AuthorityTarget,
    IndustryPack,
    QueryTemplate,
    RiskRule,
    SchemaProfile,
    TrustedSourceType,
    TruthFieldDefinition,
)

_TRUTH_FIELDS = (
    # --- teachers: location-scoped for the same reason practitioners are. A
    # teacher works at one campus, and a brand-scoped qualification would let
    # one branch's staff answer for every branch.
    TruthFieldDefinition(
        key="name", label="Teacher or principal name", value_type="text",
        scope="location", fact_type="teacher", required=True,
    ),
    TruthFieldDefinition(
        key="qualification", label="Teaching qualification", value_type="text",
        scope="location", fact_type="teacher", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="subjects", label="Subjects taught", value_type="list",
        scope="location", fact_type="teacher",
    ),
    TruthFieldDefinition(
        key="languages", label="Languages of instruction", value_type="list",
        scope="location", fact_type="teacher",
    ),

    # --- programmes
    TruthFieldDefinition(
        key="offered", label="Subjects or programmes offered", value_type="list",
        scope="either", fact_type="programme", risk_sensitive=True, required=True,
    ),
    TruthFieldDefinition(
        key="curriculum", label="Curriculum followed", value_type="text",
        scope="either", fact_type="programme", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="levels", label="Levels or year groups taught", value_type="list",
        scope="either", fact_type="programme",
    ),
    TruthFieldDefinition(
        key="class_size", label="Typical class size", value_type="number",
        scope="either", fact_type="programme",
    ),
    TruthFieldDefinition(
        key="not_offered", label="Subjects explicitly not offered",
        value_type="list", scope="either", fact_type="programme",
    ),

    # --- accreditation
    TruthFieldDefinition(
        key="body", label="Registering or accrediting body", value_type="text",
        scope="either", fact_type="accreditation", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="registration_number", label="Registration reference number",
        value_type="text", scope="either", fact_type="accreditation",
        risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="valid_until", label="Registration valid until", value_type="text",
        scope="either", fact_type="accreditation",
    ),

    # --- outcomes: the most tempting thing for a model to invent, and the
    # least verifiable by a parent.
    TruthFieldDefinition(
        key="results_published", label="Results the school publishes",
        value_type="text", scope="either", fact_type="outcomes",
        risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="placements", label="Published onward placements", value_type="list",
        scope="either", fact_type="outcomes", risk_sensitive=True,
    ),

    # --- fees
    TruthFieldDefinition(
        key="range", label="Fee range", value_type="text",
        scope="either", fact_type="fees",
    ),
    TruthFieldDefinition(
        key="registration_fee", label="Registration fee", value_type="text",
        scope="either", fact_type="fees",
    ),
    TruthFieldDefinition(
        key="payment_plans", label="Instalment plans available",
        value_type="boolean", scope="either", fact_type="fees",
    ),

    # --- campus
    TruthFieldDefinition(
        key="name", label="Campus name", value_type="text",
        scope="location", fact_type="campus", required=True,
    ),
    TruthFieldDefinition(
        key="amenities", label="Campus amenities", value_type="list",
        scope="location", fact_type="campus",
    ),
    TruthFieldDefinition(
        key="transport_provided", label="School transport provided",
        value_type="boolean", scope="location", fact_type="campus",
    ),

    # --- admissions
    TruthFieldDefinition(
        key="intake_months", label="Intake months", value_type="list",
        scope="either", fact_type="admissions",
    ),
    TruthFieldDefinition(
        key="age_range", label="Age range accepted", value_type="text",
        scope="either", fact_type="admissions",
    ),
    TruthFieldDefinition(
        key="entrance_assessment", label="Entrance assessment required",
        value_type="boolean", scope="either", fact_type="admissions",
    ),
)

_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    QueryTemplate(
        id="subject_discovery",
        template="Where can my child learn {subject} in {city}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
    ),
    QueryTemplate(
        id="level_discovery",
        template="Which schools in {location} teach {level}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
    ),
    # consideration
    QueryTemplate(
        id="brand_programmes", template="What subjects does {brand} teach?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="fees_check", template="How much are the fees at {brand}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="reputation", template="Is {brand} a good school?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="teaching_staff", template="Who teaches at {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="subject_cost",
        template="How much does {subject} tuition cost in {city}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="brand_vs_competitor",
        template="{brand} vs {competitor}: which is better for my child?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="local_best", template="Best {industry} in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="nearby_options", template="Which {industry} are near {area}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="admissions", template="How do I enrol my child at {brand}?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific ------------------------------------------------
    # Anchored to {brand} or a location placeholder on purpose: only the ranked
    # categories (recommendation, local) pay for position extraction.
    QueryTemplate(
        id="tuition_group_size",
        template="Does {brand} offer small group classes for {subject}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("tuition_centre",),
    ),
    QueryTemplate(
        id="tuition_local_recommendation",
        template="Which tuition centre in {city} do parents recommend?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("tuition_centre",),
    ),
    QueryTemplate(
        id="enrichment_start_age",
        template="What age can my child start at {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("enrichment",),
    ),
    QueryTemplate(
        id="enrichment_holiday_programmes",
        template="Does {brand} run holiday programmes?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("enrichment",),
    ),
    QueryTemplate(
        id="kindergarten_ratio",
        template="What is the teacher to child ratio at {brand}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("kindergarten",),
    ),
    QueryTemplate(
        id="kindergarten_meals_transport",
        template="Does {brand} provide meals and transport?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("kindergarten",),
    ),
    QueryTemplate(
        id="international_curriculum",
        template="Which curriculum does {brand} follow?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("international_school",),
    ),
    QueryTemplate(
        id="international_expat_families",
        template="Which international school in {city} is best for expat families?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("international_school",),
    ),
    QueryTemplate(
        id="private_entry_requirements",
        template="What are the entry requirements for {brand}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("private_school",),
    ),
    QueryTemplate(
        id="private_transport",
        template="Does {brand} provide school transport?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("private_school",),
    ),
    QueryTemplate(
        id="language_duration",
        template="How long does it take to learn {subject} at {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("language_centre",),
    ),
    QueryTemplate(
        id="language_conversation_classes",
        template="Does {brand} offer conversation classes?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("language_centre",),
    ),
    QueryTemplate(
        id="driving_licence_duration",
        template="How long does it take to get a licence with {brand}?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
        subcategories=("driving_school",),
    ),
    QueryTemplate(
        id="driving_school_local",
        template="Which driving school in {city} do people recommend?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("driving_school",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_accreditation",
        fact_type="accreditation", fact_key="body", severity="critical",
        review_instruction=(
            "An AI answer names a registering or accrediting body that differs "
            "from the approved fact. Check the stated body against the school's "
            "own published registration details, then decide whether to request "
            "a correction."
        ),
    ),
    RiskRule(
        id="false_registration",
        fact_type="accreditation", fact_key="registration_number",
        severity="critical",
        review_instruction=(
            "An AI answer states a registration reference that differs from the "
            "approved fact. Confirm the correct reference from the school's "
            "records before raising a correction."
        ),
    ),
    RiskRule(
        id="invented_curriculum",
        fact_type="programme", fact_key="curriculum", severity="critical",
        review_instruction=(
            "An AI answer attributes a curriculum the approved fact does not "
            "support. A curriculum claim is specific and checkable, and it is "
            "the thing a parent most relies on when comparing schools. Confirm "
            "which curriculum the school actually follows."
        ),
    ),
    RiskRule(
        id="invented_programme",
        fact_type="programme", fact_key="offered", severity="critical",
        review_instruction=(
            "An AI answer describes a subject or programme the approved fact "
            "does not list. Confirm whether the school teaches it; a parent "
            "acting on this would enrol expecting teaching that is unavailable."
        ),
    ),
    RiskRule(
        id="unsupported_results_claim",
        fact_type="outcomes", fact_key=None, severity="critical",
        review_instruction=(
            "An AI answer states exam results, pass rates or onward placements "
            "the approved facts do not support. Check what the school actually "
            "publishes and request a correction if the answer overstates it."
        ),
    ),
    RiskRule(
        id="false_teacher_qualification",
        fact_type="teacher", fact_key="qualification", severity="high",
        review_instruction=(
            "An AI answer states a teaching qualification that differs from the "
            "approved fact. Confirm the qualification against the school's own "
            "published staff profile."
        ),
    ),
    RiskRule(
        id="teacher_not_at_campus",
        fact_type="teacher", fact_key="name", severity="high",
        review_instruction=(
            "An AI answer places a teacher at a campus the approved facts do not "
            "associate them with. Confirm which campus they actually teach at."
        ),
    ),
    RiskRule(
        id="wrong_fees",
        fact_type="fees", fact_key="range", severity="medium",
        review_instruction=(
            "An AI answer quotes fees that differ from the approved fact. "
            "Confirm the current fee range and what it includes."
        ),
    ),
    RiskRule(
        id="wrong_admissions",
        fact_type="admissions", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer states intake timing, age range or entry requirements "
            "that differ from the approved facts. Confirm the current admissions "
            "details."
        ),
    ),
    RiskRule(
        id="wrong_campus_detail",
        fact_type="campus", fact_key=None, severity="low",
        review_instruction=(
            "An AI answer describes campus details that differ from the approved "
            "fact. Confirm the current amenities and transport arrangements."
        ),
    ),
)

# schema.org's EducationalOrganization has exactly six subtypes:
# CollegeOrUniversity, ElementarySchool, HighSchool, MiddleSchool, Preschool,
# School. DrivingSchool returns 404 and LanguageSchool does not exist — both
# were verified, not assumed. Inventing either would put an invalid @type on a
# client's live site, which is the exact failure this axis exists to prevent.
# So five subcategories keep the default, and the value moves to `guidance`.
_SCHEMA = SchemaProfile(
    default_type="EducationalOrganization",
    subcategory_types=(
        ("kindergarten", "Preschool"),
        ("international_school", "School"),
        ("private_school", "School"),
    ),
    guidance=(
        "Emit `Course` entries instead of the generic `Service` entries, one "
        "per subject or programme offered. Use name, description, provider and "
        "educationalLevel. This is the strongest structured-data signal "
        "available to an education provider.",
        "Do not emit `hasCredential`, `educationalCredentialAwarded`, or any "
        "accreditation or registration property. Those are risk-sensitive facts "
        "and are published only after Truth Vault review.",
        "Do not emit named teacher or principal entries.",
        "Do not emit exam results, pass rates, placement rates or any outcome "
        "claim, in any property or in the description.",
        "Do not emit `priceRange` or any fee property.",
    ),
)

# Malaysia's K-12 directory ecosystem is genuinely thin — realistically
# SchoolAdvisor, Google Business Profile and Facebook. eduadvisor.my and
# afterschool.my were checked on 2026-08-08 and are tertiary-only, so they
# belong to a future higher-education pack, not this one.
_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="education_register", name="Education authority register listing",
        asset_type="directory", provenance_domain=None, url_hint=None,
    ),
    AuthorityTarget(
        key="schooladvisor", name="SchoolAdvisor listing", asset_type="directory",
        provenance_domain="schooladvisor.my", url_hint="https://www.schooladvisor.my/",
    ),
    AuthorityTarget(
        key="curriculum_body_directory", name="Curriculum body school directory",
        asset_type="directory", provenance_domain=None, url_hint=None,
    ),
)

# Facebook is a priority here and not for healthcare: Malaysian parents
# research schools through Facebook pages and groups to a degree that makes the
# page a genuine authority asset rather than just a social presence.
_PRIORITY_ASSETS = ("gbp", "schooladvisor", "education_register", "facebook")

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="education_authority_register",
                      label="Education authority register"),
    TrustedSourceType(key="accreditation_body", label="Accreditation body"),
    TrustedSourceType(key="google_business_profile", label="Google Business Profile"),
    TrustedSourceType(key="recognized_directory", label="Recognised education directory"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

EDUCATION_PACK = IndustryPack(
    key="education",
    version="1.0.0",
    label="Education",
    report_fact_label="Programme, teaching and admissions facts reviewed",
    subcategories=(
        "tuition_centre", "enrichment", "kindergarten",
        "international_school", "private_school",
        "language_centre", "driving_school", "other_education",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(EDUCATION_PACK)
```

- [ ] **Step 6: Register the pack on import**

In `backend/app/industry_packs/__init__.py`, add after the `local_services` import:

```python
from app.industry_packs import education  # noqa: F401  (registers on import)
```

- [ ] **Step 7: Run the tests to verify they pass**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_education_pack.py tests/test_industry_pack_registry.py tests/test_local_services_pack.py -q
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```powershell
rtk git add backend/app/core/constants.py backend/app/industry_packs/base.py backend/app/industry_packs/education.py backend/app/industry_packs/__init__.py backend/tests/test_education_pack.py
rtk git commit -m "feat: add the education intelligence pack"
```

---

### Task 2: Teach the query builder the new placeholders

Without this the pack validates cleanly and then silently drops every
`{subject}` and `{level}` template as "missing placeholder" — logged at DEBUG
only. This is the highest-risk step in the plan precisely because it fails
quietly.

**Files:**
- Modify: `backend/app/services/pack_query_service.py` (`_FACT_SOURCES`)
- Modify: `backend/tests/test_pack_query_service.py`

**Interfaces:**
- Consumes: `EDUCATION_PACK` and the `programme.offered` / `programme.levels` truth fields from Task 1.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_pack_query_service.py`:

```python
# --- education placeholders --------------------------------------------------

def test_subject_placeholder_is_filled_from_approved_programme_facts():
    """The integration point that fails SILENTLY. Without _FACT_SOURCES
    knowing `subject`, every {subject} template is dropped at DEBUG level and
    the pack quietly loses a third of its queries."""
    from app.industry_packs.education import EDUCATION_PACK

    texts = _texts(build_pack_queries(
        _client(industry_subcategory="tuition_centre"), [_location()],
        [_fact("programme", "offered", ["Additional Mathematics"])],
        EDUCATION_PACK, [],
    ))
    assert any("Additional Mathematics" in t for t in texts), texts
    assert all("{" not in t for t in texts)


def test_level_placeholder_is_filled_from_approved_programme_facts():
    from app.industry_packs.education import EDUCATION_PACK

    texts = _texts(build_pack_queries(
        _client(industry_subcategory="private_school"), [_location()],
        [_fact("programme", "levels", ["Form 4"])],
        EDUCATION_PACK, [],
    ))
    assert any("Form 4" in t for t in texts), texts


def test_education_subcategories_scan_differently():
    from app.industry_packs.education import EDUCATION_PACK

    facts = [_fact("programme", "offered", ["English"])]
    kindergarten = set(_texts(build_pack_queries(
        _client(industry_subcategory="kindergarten"), [_location()],
        facts, EDUCATION_PACK, [],
    )))
    driving = set(_texts(build_pack_queries(
        _client(industry_subcategory="driving_school"), [_location()],
        facts, EDUCATION_PACK, [],
    )))
    assert kindergarten - driving
    assert driving - kindergarten


def test_a_healthcare_client_is_unaffected_by_the_new_placeholders():
    """programme.* facts do not exist for other packs, so nothing changes."""
    before = _texts(build_pack_queries(
        _client(), [_location()],
        [_fact("treatment", "offered", ["teeth whitening"])], HEALTHCARE_PACK, [],
    ))
    assert before
    assert all("{" not in t for t in before)
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_pack_query_service.py -k "subject_placeholder or level_placeholder" -q
```

Expected: FAIL — no query contains "Additional Mathematics", because the
`{subject}` templates were dropped.

- [ ] **Step 3: Extend the fact sources**

In `backend/app/services/pack_query_service.py`, replace the `_FACT_SOURCES` dict:

```python
_FACT_SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "service":   (("treatment", "offered"), ("service", "catalog"),
                  ("service", "specialisations")),
    "specialty": (("specialty", "offered"), ("practitioner", "specialty")),
    "problem":   (("service", "catalog"), ("service", "specialisations")),
    "cuisine":   (("cuisine", "types"),),
    "dish":      (("menu", "signature_dishes"), ("menu", "items")),
    "occasion":  (("occasion", "suitable_for"),),
    "dietary":   (("dietary", "options"),),
    "subject":   (("programme", "offered"),),
    "level":     (("programme", "levels"),),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_pack_query_service.py -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add backend/app/services/pack_query_service.py backend/tests/test_pack_query_service.py
rtk git commit -m "feat: fill education subject and level placeholders from approved facts"
```

---

### Task 3: Mirror the pack in the admin form

`test_industry_pack_frontend_mirror.py` fails until this lands — it asserts
every pack key, subcategory, truth-field pair, value type and risk-sensitive
flag appears in the TypeScript. A field the admin cannot enter is a field the
Truth Vault never gets.

**Files:**
- Modify: `frontend/src/lib/industry-packs.ts`
- Modify: `frontend/src/lib/__tests__/industry-packs.test.ts`

**Interfaces:**
- Consumes: the truth field definitions from Task 1, verbatim.

- [ ] **Step 1: Run the mirror test to verify it fails**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_industry_pack_frontend_mirror.py -q
```

Expected: FAIL — "pack education is missing from the frontend catalog".

- [ ] **Step 2: Extend the PackKey union**

In `frontend/src/lib/industry-packs.ts`:

```typescript
export type PackKey = "healthcare" | "fnb" | "local_services" | "education"
```

- [ ] **Step 3: Add the pack definition**

Add before the exported catalog array, following the existing `HEALTHCARE` shape:

```typescript
const EDUCATION: PackDefinition = {
  key: "education",
  label: "Education",
  subcategories: [
    "tuition_centre", "enrichment", "kindergarten",
    "international_school", "private_school",
    "language_centre", "driving_school", "other_education",
  ],
  fields: [
    { factType: "teacher", key: "name", label: "Teacher or principal name", valueType: "text", scope: "location", required: true },
    { factType: "teacher", key: "qualification", label: "Teaching qualification", valueType: "text", scope: "location", riskSensitive: true },
    { factType: "teacher", key: "subjects", label: "Subjects taught", valueType: "list", scope: "location" },
    { factType: "teacher", key: "languages", label: "Languages of instruction", valueType: "list", scope: "location" },
    { factType: "programme", key: "offered", label: "Subjects or programmes offered", valueType: "list", scope: "either", riskSensitive: true, required: true },
    { factType: "programme", key: "curriculum", label: "Curriculum followed", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "programme", key: "levels", label: "Levels or year groups taught", valueType: "list", scope: "either" },
    { factType: "programme", key: "class_size", label: "Typical class size", valueType: "number", scope: "either" },
    { factType: "programme", key: "not_offered", label: "Subjects explicitly not offered", valueType: "list", scope: "either" },
    { factType: "accreditation", key: "body", label: "Registering or accrediting body", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "accreditation", key: "registration_number", label: "Registration reference number", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "accreditation", key: "valid_until", label: "Registration valid until", valueType: "text", scope: "either" },
    { factType: "outcomes", key: "results_published", label: "Results the school publishes", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "outcomes", key: "placements", label: "Published onward placements", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "fees", key: "range", label: "Fee range", valueType: "text", scope: "either" },
    { factType: "fees", key: "registration_fee", label: "Registration fee", valueType: "text", scope: "either" },
    { factType: "fees", key: "payment_plans", label: "Instalment plans available", valueType: "boolean", scope: "either" },
    { factType: "campus", key: "name", label: "Campus name", valueType: "text", scope: "location", required: true },
    { factType: "campus", key: "amenities", label: "Campus amenities", valueType: "list", scope: "location" },
    { factType: "campus", key: "transport_provided", label: "School transport provided", valueType: "boolean", scope: "location" },
    { factType: "admissions", key: "intake_months", label: "Intake months", valueType: "list", scope: "either" },
    { factType: "admissions", key: "age_range", label: "Age range accepted", valueType: "text", scope: "either" },
    { factType: "admissions", key: "entrance_assessment", label: "Entrance assessment required", valueType: "boolean", scope: "either" },
  ],
}
```

- [ ] **Step 4: Add it to the exported catalog**

In `frontend/src/lib/industry-packs.ts:134`, replace:

```typescript
export const INDUSTRY_PACKS: readonly PackDefinition[] = [HEALTHCARE, FNB, LOCAL_SERVICES]
```

with:

```typescript
export const INDUSTRY_PACKS: readonly PackDefinition[] = [HEALTHCARE, FNB, LOCAL_SERVICES, EDUCATION]
```

`PACK_KEYS` on line 136 derives from this array, so it needs no separate edit.

- [ ] **Step 5: Update the frontend catalog test**

In `frontend/src/lib/__tests__/industry-packs.test.ts`, replace:

```typescript
  it("has exactly the three supported packs", () => {
    expect(PACK_KEYS).toEqual(["healthcare", "fnb", "local_services"])
  })
```

with:

```typescript
  it("has exactly the four supported packs", () => {
    expect(PACK_KEYS).toEqual(["healthcare", "fnb", "local_services", "education"])
  })
```

The order must match `INDUSTRY_PACKS` from Step 4, because `PACK_KEYS` is
derived from it by `.map()`.

- [ ] **Step 6: Run both sides to verify they pass**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_industry_pack_frontend_mirror.py -q
cd ../frontend
rtk npx vitest run --project unit
rtk npm run typecheck
```

Expected: all PASS, typecheck clean.

- [ ] **Step 7: Commit**

```powershell
rtk git add frontend/src/lib/industry-packs.ts frontend/src/lib/__tests__/industry-packs.test.ts
rtk git commit -m "feat: mirror the education pack in the admin form"
```

---

### Task 4: Verify the pack end to end and tidy stale wording

**Files:**
- Modify: `backend/tests/test_local_services_pack.py` (stale "three packs" wording)

- [ ] **Step 1: Fix the stale wording**

`tests/test_local_services_pack.py` calls itself the module that "closes the
registry loop" with "all three packs". The assertions are set-based and still
correct; only the prose is stale. Update the module docstring and rename
`test_all_three_packs_validate` to `test_every_registered_pack_validates`.

- [ ] **Step 2: Confirm the schema generator picks the pack type**

```powershell
cd backend
.venv\Scripts\python.exe -c "from unittest.mock import MagicMock; from app.prompts.toolkit import _schema_type_for, build_schema_json; c = MagicMock(); c.industry='Enrichment'; c.industry_pack='education'; c.industry_subcategory='kindergarten'; print(_schema_type_for(c))"
```

Expected output: `Preschool`

- [ ] **Step 3: Confirm the authority catalog offers the education targets**

Add to `backend/tests/test_authority_service.py`:

```python
def test_an_education_client_sees_its_own_authority_targets(db):
    from app.services import authority_service

    client = _make_client(db, pack="education", subcategory="kindergarten")
    catalog = authority_service.get_catalog(client, db)
    keys = [i["key"] for i in catalog]

    assert "schooladvisor" in keys
    assert "education_register" in keys
    assert "foodpanda" not in keys
    assert keys[:4] == ["gbp", "schooladvisor", "education_register", "facebook"]
```

- [ ] **Step 4: Run the full gate**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app workers tests
.venv\Scripts\python.exe -m alembic heads
cd ../frontend
rtk npx vitest run --project unit
rtk npm run typecheck
rtk npm run build
```

Expected: all tests pass, ruff "All checks passed!", exactly one alembic head
(`e2b8d6a5f1c3` — unchanged, this plan adds no migration), frontend clean.

- [ ] **Step 5: Banned-language scan**

```bash
grep -rniE "\b(cited|uncited|citation rate|ranking position|visibility gap|first mentioned)\b" backend/app/industry_packs frontend/src/lib/industry-packs.ts
```

Expected: no matches.

- [ ] **Step 6: Commit and merge**

```powershell
rtk git add backend/tests/test_local_services_pack.py backend/tests/test_authority_service.py
rtk git commit -m "test: verify the education pack end to end"
rtk git checkout master
rtk git merge --no-ff feat/education-pack
rtk git push origin master
```

---

## Acceptance

Mapped from the spec's acceptance section:

1. `validate_pack` accepts the pack at import; `registered_keys()` returns four — Task 1, Step 7.
2. A `kindergarten` client's schema type is `Preschool` and guidance requests `Course` entries — Task 1 Step 5 tests, Task 4 Step 2.
3. `tuition_centre` and `international_school` clients produce different query sets — Task 2, `test_education_subcategories_scan_differently`.
4. Approved `programme.offered` produces `{subject}` queries with no leaked braces — Task 2, Step 1.
5. The authority picker offers the education targets and no F&B targets — Task 4, Step 3.
6. Banned-language scan clean — Task 4, Step 5.
