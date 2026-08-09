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
        template="Where can I learn {subject} in {city}?",
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
        template="How much does {subject} cost in {city}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="brand_vs_competitor",
        template="{brand} vs {competitor}: which is better?",
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
        id="admissions", template="How do I enrol at {brand}?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific ------------------------------------------------
    # Anchored to {brand} or a location placeholder on purpose, and each
    # anchor is chosen to match what the question can pay for:
    #   - {brand}-anchored yes/no questions land in `brand` (not ranked),
    #     which is correct — a yes/no answer has no ranking to extract.
    #   - Location-anchored "which X in {city}" questions land in `local`
    #     (ranked), which is also correct — those are genuine ranked-list
    #     questions worth the extra position-extraction call.
    # What to avoid is an UNANCHORED template: `category_for` would fall
    # through it to `recommendation` (ranked), buying a position-extraction
    # call a yes/no or small-group question can never use.
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
