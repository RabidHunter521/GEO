"""Renovation and interior design intelligence pack.

For renovation contractors, interior designers, design-and-build firms, built-in
carpentry (kitchen cabinets, wardrobes) and landscapers. Small repair and
maintenance trades (plumbing, aircon, pest control) stay in Local Services.

Renovation is a large, deposit-first purchase and the sector buyers trust
least, so the defining risks are the claims that decide whether an owner hands
over a deposit: a contractor registration the firm does not hold, a workmanship
warranty or insurance it does not give, payment terms it does not offer, and an
area it does not serve. A wrong price is corrected at the site visit; a deposit
paid on a false registration claim is not.

Discovery questions come from the approved types of work, property types and
design styles ("Cost of kitchen renovation in Malaysia", "Best
contractor for condo renovation in Petaling Jaya"), because an owner searches
for the job, not the firm.

Instructions describe what a reviewer should CHECK. None asserts that a firm is
or is not registered -- SeenBy reports what an AI system said.
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
    # --- the work
    TruthFieldDefinition(
        key="types",
        label="Types of work (e.g. kitchen renovation, bathroom, extension, wardrobes)",
        value_type="list", scope="either", fact_type="work", required=True,
    ),
    TruthFieldDefinition(
        key="property_types", label="Property types (e.g. condo, landed house, shop lot)",
        value_type="list", scope="either", fact_type="work",
    ),
    TruthFieldDefinition(
        key="not_offered", label="Work not taken on", value_type="list",
        scope="either", fact_type="work",
    ),
    TruthFieldDefinition(
        key="styles", label="Design styles (e.g. modern minimalist, Japandi)",
        value_type="list", scope="either", fact_type="design",
    ),
    TruthFieldDefinition(
        key="track_record", label="Completed projects or portfolio", value_type="text",
        scope="either", fact_type="project",
    ),

    # --- where: a wrong area wastes a site visit, so it is risk-sensitive
    TruthFieldDefinition(
        key="areas", label="Areas served", value_type="list",
        scope="either", fact_type="coverage", required=True, risk_sensitive=True,
    ),

    # --- who stands behind the work: all risk-sensitive
    TruthFieldDefinition(
        key="contractor_registration",
        label="Contractor registration (e.g. CIDB grade and number)",
        value_type="text", scope="brand", fact_type="registration", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="held", label="Licences and certifications held", value_type="list",
        scope="either", fact_type="licensing", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="public_liability", label="Public liability cover", value_type="text",
        scope="either", fact_type="insurance", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="workmanship_cover", label="Workmanship cover", value_type="text",
        scope="either", fact_type="insurance", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="terms", label="Workmanship warranty or defect liability terms",
        value_type="text", scope="either", fact_type="warranty", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="duration", label="Warranty duration", value_type="text",
        scope="either", fact_type="warranty",
    ),

    # --- money
    TruthFieldDefinition(
        key="price_range", label="Typical project price range", value_type="text",
        scope="either", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="model", label="Pricing model (e.g. per sq ft, lump sum, design fee)",
        value_type="text", scope="either", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="free_quote", label="Free quotation or site visit", value_type="boolean",
        scope="either", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="schedule", label="Deposit and progress payment terms", value_type="text",
        scope="either", fact_type="payment", risk_sensitive=True,
    ),
)

# {work_type}, {property_type} and {style} come from approved facts only.
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    # consideration
    QueryTemplate(
        id="brand_trustworthy", template="Is {brand} a trustworthy {industry}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="work_cost", template="Cost of {work_type} in {country}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="reliable_local", template="Reliable {industry} in {location}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="work_best_city", template="Best company for {work_type} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="property_type_city", template="Best contractor for {property_type} renovation in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="city_best", template="Best {industry} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} vs {competitor}: which is better?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific (at most four each; registry test) ------------
    QueryTemplate(
        id="gc_reliable", template="Reliable renovation contractor in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("general_contractor",),
    ),
    QueryTemplate(
        id="gc_warranty", template="Renovation contractor with warranty in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("general_contractor",),
    ),
    QueryTemplate(
        id="gc_brand_registered", template="Is {brand} a registered contractor?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("general_contractor", "design_and_build"),
    ),
    QueryTemplate(
        id="id_best", template="Best interior designer in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("interior_designer",),
    ),
    QueryTemplate(
        id="id_style", template="Interior designer for {style} style in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("interior_designer", "design_and_build"),
    ),
    QueryTemplate(
        id="id_cost", template="How much does an interior designer cost in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("interior_designer",),
    ),
    QueryTemplate(
        id="db_best", template="Best design and build renovation company in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("design_and_build",),
    ),
    QueryTemplate(
        id="carp_kitchen", template="Best kitchen cabinet maker in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("carpentry",),
    ),
    QueryTemplate(
        id="carp_wardrobe", template="Custom built-in wardrobe in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("carpentry",),
    ),
    QueryTemplate(
        id="carp_brand_warranty", template="Does {brand} give a warranty on cabinets?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("carpentry",),
    ),
    QueryTemplate(
        id="land_best", template="Best landscape designer in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("landscape",),
    ),
    QueryTemplate(
        id="land_cost", template="How much does garden landscaping cost in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("landscape",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_contractor_registration",
        fact_type="registration", fact_key="contractor_registration", severity="critical",
        review_instruction=(
            "An AI answer states a contractor registration or grade that differs "
            "from the approved fact. Check the registration body's public search "
            "before responding; an owner may pay a deposit on the strength of that "
            "answer."
        ),
    ),
    RiskRule(
        id="wrong_payment_terms",
        fact_type="payment", fact_key="schedule", severity="high",
        review_instruction=(
            "An AI answer describes deposit or progress payment terms that differ "
            "from the approved fact. Confirm the terms in the firm's standard "
            "contract."
        ),
    ),
    RiskRule(
        id="wrong_warranty",
        fact_type="warranty", fact_key="terms", severity="high",
        review_instruction=(
            "An AI answer describes warranty or defect liability terms that differ "
            "from the approved fact. Confirm what is covered and for how long."
        ),
    ),
    RiskRule(
        id="wrong_insurance",
        fact_type="insurance", fact_key=None, severity="high",
        review_instruction=(
            "An AI answer describes insurance cover that differs from the approved "
            "facts. Confirm against the current policy schedule."
        ),
    ),
    RiskRule(
        id="wrong_licence",
        fact_type="licensing", fact_key="held", severity="high",
        review_instruction=(
            "An AI answer states a licence or certification that differs from the "
            "approved fact. Check the issuing body's register before responding."
        ),
    ),
    RiskRule(
        id="wrong_service_area",
        fact_type="coverage", fact_key="areas", severity="medium",
        review_instruction=(
            "An AI answer says the firm works in an area the approved fact does not "
            "list. Confirm where it takes on projects."
        ),
    ),
    RiskRule(
        id="invented_work",
        fact_type="work", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer says the firm does work the approved facts do not list. "
            "Confirm what it takes on."
        ),
    ),
    RiskRule(
        id="wrong_price",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes prices that differ from the approved facts. Confirm "
            "the current price range and pricing model."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="contractor_register", label="Contractor registration body's search"),
    TrustedSourceType(key="company_registry", label="Company registry (e.g. SSM)"),
    TrustedSourceType(key="standard_contract", label="Standard contract or quotation terms"),
    TrustedSourceType(key="insurance_schedule", label="Insurance policy schedule"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

_SCHEMA = SchemaProfile(
    default_type="HomeAndConstructionBusiness",
    subcategory_types=(
        ("general_contractor", "GeneralContractor"),
        ("design_and_build", "GeneralContractor"),
    ),
    guidance=(
        "Add `areaServed` only for areas the description names.",
        "Do not emit prices, per-square-foot rates or promotions; they depend on "
        "the job.",
        "Do not emit contractor registration, licence, insurance, warranty or "
        "payment-term claims. Those are risk-sensitive facts requiring an approved "
        "source.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="qanvast", name="Qanvast profile", asset_type="directory",
        provenance_domain="qanvast.com", url_hint="https://qanvast.com/my",
    ),
    AuthorityTarget(
        key="recommend_my", name="Recommend.my listing", asset_type="directory",
        provenance_domain="recommend.my", url_hint="https://recommend.my/",
    ),
    AuthorityTarget(
        key="houzz", name="Houzz profile", asset_type="directory",
        provenance_domain="houzz.com", url_hint="https://www.houzz.com/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "qanvast", "facebook", "instagram")

RENOVATION_PACK = IndustryPack(
    key="renovation",
    version="1.0.0",
    report_fact_label="Work, registration and warranty information reviewed",
    label="Renovation & Interior Design",
    subcategories=(
        "general_contractor", "interior_designer", "design_and_build", "carpentry",
        "landscape", "other_renovation",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(RENOVATION_PACK)
