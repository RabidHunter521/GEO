"""Healthcare intelligence pack.

Specializes scanning and accuracy triage for clinics, dental practices,
specialists and similar providers. What makes healthcare different from the
other packs is the asymmetry of harm: a wrong opening time costs a buyer a
trip, whereas a wrong qualification or an invented treatment can send someone
to a provider who cannot actually treat them. The risk rules encode exactly
that asymmetry.

Every instruction tells a reviewer what to CHECK. None asserts that anything is
illegal, unlicensed or non-compliant — SeenBy observes what AI systems say, and
is not in a position to adjudicate a regulatory question. The base validator
enforces this, so it cannot drift.
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
    # --- practitioners: location-scoped, because a doctor practises somewhere
    # specific and a brand-scoped credential would let one branch's staff answer
    # for every branch.
    TruthFieldDefinition(
        key="name", label="Practitioner name", value_type="text",
        scope="location", fact_type="practitioner", required=True,
    ),
    TruthFieldDefinition(
        key="qualification", label="Qualification", value_type="text",
        scope="location", fact_type="practitioner", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="registration_number", label="Professional registration number",
        value_type="text", scope="location", fact_type="practitioner",
        risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="specialty", label="Practitioner specialty", value_type="text",
        scope="location", fact_type="practitioner", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="languages", label="Languages spoken", value_type="list",
        scope="location", fact_type="practitioner",
    ),

    # --- specialties offered by the practice as a whole
    TruthFieldDefinition(
        key="offered", label="Specialties offered", value_type="list",
        scope="either", fact_type="specialty", risk_sensitive=True, required=True,
    ),

    # --- treatments
    TruthFieldDefinition(
        key="offered", label="Treatments offered", value_type="list",
        scope="either", fact_type="treatment", risk_sensitive=True, required=True,
    ),
    TruthFieldDefinition(
        key="not_offered", label="Treatments explicitly not offered",
        value_type="list", scope="either", fact_type="treatment",
    ),
    TruthFieldDefinition(
        key="price_range", label="Treatment price range", value_type="text",
        scope="either", fact_type="treatment",
    ),

    # --- accreditation
    TruthFieldDefinition(
        key="body", label="Accrediting body", value_type="text",
        scope="either", fact_type="accreditation", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="valid_until", label="Accreditation valid until", value_type="text",
        scope="either", fact_type="accreditation",
    ),

    # --- facility
    TruthFieldDefinition(
        key="name", label="Facility name", value_type="text",
        scope="location", fact_type="facility", required=True,
    ),
    TruthFieldDefinition(
        key="services", label="On-site services", value_type="list",
        scope="location", fact_type="facility",
    ),
    TruthFieldDefinition(
        key="accessibility", label="Accessibility provisions", value_type="list",
        scope="location", fact_type="facility",
    ),

    # --- payment
    TruthFieldDefinition(
        key="methods", label="Payment methods accepted", value_type="list",
        scope="either", fact_type="payment",
    ),
    TruthFieldDefinition(
        key="insurance_panels", label="Insurance panels accepted", value_type="list",
        scope="either", fact_type="payment", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="instalment_available", label="Instalment plans available",
        value_type="boolean", scope="either", fact_type="payment",
    ),
)

_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    QueryTemplate(
        id="treatment_discovery", template="Where can I get {service} in {city}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
    ),
    QueryTemplate(
        id="specialty_discovery", template="Which clinics offer {specialty} in {location}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
    ),
    # consideration
    QueryTemplate(
        id="practitioner_lookup",
        template="Who are the {specialty} practitioners at {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="treatment_cost", template="How much does {service} cost in {city}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="eligibility", template="Am I suitable for {service}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="brand_services", template="What treatments does {brand} offer?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="insurance_accepted", template="Does {brand} accept insurance?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    # decision
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} vs {competitor}: which is better?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="local_best", template="Best {industry} in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="local_recommendation", template="Recommend a {specialty} clinic near {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="booking", template="How do I book an appointment with {brand}?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_credentials",
        fact_type="practitioner", fact_key="qualification", severity="critical",
        review_instruction=(
            "An AI answer states a qualification that differs from the approved fact. "
            "Check the stated qualification against the practice's own published "
            "profile and the relevant professional register, then decide whether to "
            "request a correction."
        ),
    ),
    RiskRule(
        id="false_registration",
        fact_type="practitioner", fact_key="registration_number", severity="critical",
        review_instruction=(
            "An AI answer states a registration number that differs from the approved "
            "fact. Confirm the correct number from the practice's records before "
            "raising a correction."
        ),
    ),
    RiskRule(
        id="wrong_specialty",
        fact_type="practitioner", fact_key="specialty", severity="high",
        review_instruction=(
            "An AI answer attributes a specialty the approved fact does not support. "
            "Confirm which specialty this practitioner actually practises."
        ),
    ),
    RiskRule(
        id="invented_treatment",
        fact_type="treatment", fact_key="offered", severity="critical",
        review_instruction=(
            "An AI answer describes a treatment the approved fact does not list as "
            "offered. Confirm whether the practice provides it; a buyer acting on "
            "this would arrive expecting care that is unavailable."
        ),
    ),
    RiskRule(
        id="unsupported_outcome_claim",
        fact_type="treatment", fact_key=None, severity="critical",
        review_instruction=(
            "An AI answer promises a treatment result the approved facts do not "
            "support. Check what the practice actually publishes about expected "
            "outcomes and request a correction if the answer overstates it."
        ),
    ),
    RiskRule(
        id="practitioner_not_at_location",
        fact_type="practitioner", fact_key="name", severity="high",
        review_instruction=(
            "An AI answer places a practitioner at a location the approved facts do "
            "not associate them with. Confirm which branch they actually practise at."
        ),
    ),
    RiskRule(
        id="false_accreditation",
        fact_type="accreditation", fact_key="body", severity="high",
        review_instruction=(
            "An AI answer states an accreditation that differs from the approved "
            "fact. Confirm the current accreditation and its validity date."
        ),
    ),
    RiskRule(
        id="wrong_insurance_panel",
        fact_type="payment", fact_key="insurance_panels", severity="high",
        review_instruction=(
            "An AI answer lists an insurance panel the approved fact does not "
            "include. Confirm the current panel list; a buyer could arrive expecting "
            "cover that does not apply."
        ),
    ),
    RiskRule(
        id="wrong_specialty_offered",
        fact_type="specialty", fact_key="offered", severity="medium",
        review_instruction=(
            "An AI answer lists a specialty the practice does not record as offered. "
            "Confirm the current service list."
        ),
    ),
    RiskRule(
        id="wrong_facility_detail",
        fact_type="facility", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes facility details that differ from the approved "
            "fact. Confirm the current on-site services and access provisions."
        ),
    ),
    RiskRule(
        id="wrong_payment_detail",
        fact_type="payment", fact_key="methods", severity="low",
        review_instruction=(
            "An AI answer lists payment methods that differ from the approved fact. "
            "Confirm what the practice currently accepts."
        ),
    ),
)

# Deliberately generic categories rather than named national bodies, so the pack
# works outside Malaysia without a code change. Which specific register counts
# is a per-client Truth Vault fact, not a pack constant.
_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="professional_registry", label="Professional register"),
    TrustedSourceType(key="accreditation_body", label="Accreditation body"),
    TrustedSourceType(key="google_business_profile", label="Google Business Profile"),
    TrustedSourceType(key="recognized_directory", label="Recognised healthcare directory"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

# Every type below is a real schema.org MedicalBusiness/MedicalOrganization
# subtype. `aesthetic` maps to MedicalClinic rather than HealthAndBeautyBusiness
# because an aesthetic practice with registered practitioners is a clinic; the
# beauty type sits under LocalBusiness and would drop the medical semantics.
_SCHEMA = SchemaProfile(
    default_type="MedicalBusiness",
    subcategory_types=(
        ("general_clinic", "MedicalClinic"),
        ("dental", "Dentist"),
        ("specialist", "Physician"),
        ("aesthetic", "MedicalClinic"),
        ("physiotherapy", "Physiotherapy"),
        ("diagnostics", "DiagnosticLab"),
        ("pharmacy", "Pharmacy"),
    ),
    guidance=(
        "Add `medicalSpecialty` to the primary business entry only when the "
        "description states a specialty outright. Do not infer one.",
        "Do not emit `employee`, `Physician` or any named-practitioner entry. "
        "Practitioner names, qualifications and registration numbers are "
        "risk-sensitive facts and are published only after Truth Vault review.",
        "Do not emit `priceRange` or any price property. Treatment pricing is "
        "a reviewed fact and belongs nowhere in generated markup.",
        "Service entries describe treatments offered. Never state or imply an "
        "outcome, success rate or recovery time.",
    ),
)

# Deliberately generic where a register is country-specific: the pack works
# outside Malaysia, so "Professional register profile" carries no domain and the
# admin fills in the real one. MyHEALTH already exists in the shared catalog.
_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="medical_register", name="Professional register profile",
        asset_type="directory", provenance_domain=None, url_hint=None,
    ),
    AuthorityTarget(
        key="doctoroncall", name="DoctorOnCall listing", asset_type="directory",
        provenance_domain="doctoroncall.com.my", url_hint="https://www.doctoroncall.com.my/",
    ),
    AuthorityTarget(
        key="bookdoc", name="BookDoc listing", asset_type="directory",
        provenance_domain="bookdoc.com", url_hint="https://www.bookdoc.com/",
    ),
    AuthorityTarget(
        key="whatclinic", name="WhatClinic listing", asset_type="directory",
        provenance_domain="whatclinic.com", url_hint="https://www.whatclinic.com/",
    ),
    AuthorityTarget(
        key="insurer_panel", name="Insurance panel listing", asset_type="directory",
        provenance_domain=None, url_hint=None,
    ),
)

_PRIORITY_ASSETS = ("gbp", "myhealth_clinic", "medical_register", "doctoroncall")

HEALTHCARE_PACK = IndustryPack(
    key="healthcare",
    version="1.0.0",
    report_fact_label="Practitioner and treatment facts reviewed",
    label="Healthcare",
    subcategories=(
        "general_clinic", "dental", "specialist", "aesthetic",
        "physiotherapy", "diagnostics", "pharmacy", "other_healthcare",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(HEALTHCARE_PACK)
