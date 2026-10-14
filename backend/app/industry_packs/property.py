"""Property intelligence pack.

For developers, real estate agencies, property managers and co-living or
serviced-apartment operators.

A property buyer commits more money on an AI answer than any other client's
customer, so the defining risks are claims that change what is being bought:
the tenure (freehold vs leasehold), whether a project is finished, a licence or
registration the business does not hold, and incentives that are not on offer.
A wrong price range is inconvenient by comparison.

Discovery questions are pinned to the areas and property types the client
actually sells (approved `project.areas` / `project.types` facts), because a
buyer asks "new condo launches in Cyberjaya", not "best property developer".

Instructions describe what a reviewer should CHECK. None asserts that a
business is or is not licensed -- SeenBy reports what an AI system said and
cannot adjudicate who holds a licence.
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
    # --- what is sold or let
    TruthFieldDefinition(
        key="names", label="Projects, developments or buildings", value_type="list",
        scope="either", fact_type="project", required=True,
    ),
    TruthFieldDefinition(
        key="areas", label="Areas with projects or listings", value_type="list",
        scope="either", fact_type="project", required=True,
    ),
    TruthFieldDefinition(
        key="types", label="Property types (e.g. condominium, landed, shop lot)",
        value_type="list", scope="either", fact_type="project",
    ),
    TruthFieldDefinition(
        key="tenure", label="Tenure (freehold or leasehold)", value_type="text",
        scope="either", fact_type="project", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="completion", label="Completion or handover status", value_type="text",
        scope="either", fact_type="project", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="track_record", label="Completed projects or track record", value_type="text",
        scope="brand", fact_type="project",
    ),

    # --- services (agencies, property managers)
    TruthFieldDefinition(
        key="catalog", label="Services offered", value_type="list",
        scope="brand", fact_type="service",
    ),

    # --- pricing
    TruthFieldDefinition(
        key="price_range", label="Price range", value_type="text",
        scope="either", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="rental_range", label="Rental range", value_type="text",
        scope="either", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="offers", label="Current buyer incentives (e.g. rebates, free legal fees)",
        value_type="list", scope="either", fact_type="incentive", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="partner_banks", label="Partner banks for financing", value_type="list",
        scope="either", fact_type="financing",
    ),

    # --- licensing and registration: every one of these is risk-sensitive
    TruthFieldDefinition(
        key="developer_licence", label="Housing developer licence number",
        value_type="text", scope="brand", fact_type="registration", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="agency_registration", label="Estate agency registration number",
        value_type="text", scope="brand", fact_type="registration", risk_sensitive=True,
    ),

    # --- facilities
    TruthFieldDefinition(
        key="amenities", label="Facilities", value_type="list",
        scope="location", fact_type="facility",
    ),
)

# {district} and {property_type} come from approved project facts, so a
# question is only asked about places and property types the client sells.
# Neither is a LOCATION placeholder: they are facts, not the client's address,
# so those questions land in `recommendation` (ranked) by design.
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    QueryTemplate(
        id="district_worth_buying",
        template="Is {district} a good place to buy property?",
        buyer_stage="awareness", commercial_intent="medium", location_required=False,
    ),
    # consideration
    QueryTemplate(
        id="brand_reliable", template="Is {brand} a reliable {industry}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="type_in_district", template="Where can I buy a {property_type} in {district}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="country_top", template="Which {industry} is the best in {country}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="local_best", template="Best {industry} in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="city_trusted", template="Most trusted {industry} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="new_projects_district",
        template="Best new {property_type} projects in {district}",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} vs {competitor}: which is better?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific (at most four each; registry test) ------------
    QueryTemplate(
        id="dev_upcoming_launches", template="Upcoming property launches in {district}",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("developer",),
    ),
    QueryTemplate(
        id="dev_build_quality",
        template="Which property developers in {location} have good build quality?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("developer",),
    ),
    QueryTemplate(
        id="dev_brand_track_record",
        template="Has {brand} delivered its past projects on time?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
        subcategories=("developer",),
    ),
    QueryTemplate(
        id="agency_sell",
        template="Which real estate agency should I use to sell my property in {city}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("real_estate_agency",),
    ),
    QueryTemplate(
        id="agency_rent_out",
        template="Best property agent for renting out a condo in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("real_estate_agency",),
    ),
    QueryTemplate(
        id="agency_brand_commission", template="How much commission does {brand} charge?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("real_estate_agency",),
    ),
    QueryTemplate(
        id="pm_best", template="Best property management company in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("property_management",),
    ),
    QueryTemplate(
        id="pm_manage_rental", template="Who can manage my rental property in {city}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("property_management",),
    ),
    QueryTemplate(
        id="pm_brand_fees", template="What does {brand} charge to manage a property?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("property_management",),
    ),
    QueryTemplate(
        id="coliving_best", template="Best co-living spaces in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("co_living",),
    ),
    QueryTemplate(
        id="coliving_bills_included",
        template="Room rental with all bills included in {city}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("co_living",),
    ),
    QueryTemplate(
        id="coliving_brand_included", template="What is included in the rent at {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("co_living",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="wrong_tenure",
        fact_type="project", fact_key="tenure", severity="critical",
        review_instruction=(
            "An AI answer states a tenure that differs from the approved fact. Check "
            "the title details or the developer's published information; a buyer may "
            "commit to a purchase on the strength of that answer."
        ),
    ),
    RiskRule(
        id="wrong_registration",
        fact_type="registration", fact_key=None, severity="critical",
        review_instruction=(
            "An AI answer states a developer licence or agency registration that "
            "differs from the approved fact. Check the relevant public register "
            "before responding."
        ),
    ),
    RiskRule(
        id="wrong_completion_status",
        fact_type="project", fact_key="completion", severity="high",
        review_instruction=(
            "An AI answer describes a project's completion or handover status "
            "differently from the approved fact. Confirm the current status with "
            "the business."
        ),
    ),
    RiskRule(
        id="invented_incentive",
        fact_type="incentive", fact_key="offers", severity="high",
        review_instruction=(
            "An AI answer describes a buyer incentive the approved facts do not list. "
            "Confirm what is on offer now; a buyer could arrive expecting it."
        ),
    ),
    RiskRule(
        id="invented_project",
        fact_type="project", fact_key="names", severity="high",
        review_instruction=(
            "An AI answer attributes a project or building to the business that the "
            "approved facts do not list. Confirm which projects are theirs."
        ),
    ),
    RiskRule(
        id="wrong_price",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes prices or rents that differ from the approved fact. "
            "Confirm the current price or rental range."
        ),
    ),
    RiskRule(
        id="wrong_area",
        fact_type="project", fact_key="areas", severity="medium",
        review_instruction=(
            "An AI answer places the business's projects or listings in an area the "
            "approved fact does not list. Confirm where it operates."
        ),
    ),
    RiskRule(
        id="wrong_financing_partner",
        fact_type="financing", fact_key="partner_banks", severity="low",
        review_instruction=(
            "An AI answer names financing partners that differ from the approved "
            "fact. Confirm the current panel of banks."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="developer_register", label="Housing developer register"),
    TrustedSourceType(key="agency_register", label="Estate agency register"),
    TrustedSourceType(key="property_portal", label="Property portal listing"),
    TrustedSourceType(key="title_records", label="Land title records"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

# Developers have no customer-facing shopfront, so they default to
# Organization. LodgingBusiness is the closest real schema.org type for
# co-living and serviced apartments.
_SCHEMA = SchemaProfile(
    default_type="Organization",
    subcategory_types=(
        ("real_estate_agency", "RealEstateAgent"),
        ("property_management", "RealEstateAgent"),
        ("co_living", "LodgingBusiness"),
    ),
    guidance=(
        "Prefer `areaServed` with the areas the description names.",
        "Do not emit prices, rents or buyer incentives; they change often and "
        "an outdated figure on the client's own site misleads buyers.",
        "Do not emit tenure, completion status, licence or registration claims. "
        "Those are risk-sensitive facts requiring an approved source.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="propertyguru", name="PropertyGuru listing", asset_type="directory",
        provenance_domain="propertyguru.com.my", url_hint="https://www.propertyguru.com.my/",
    ),
    AuthorityTarget(
        key="iproperty", name="iProperty listing", asset_type="directory",
        provenance_domain="iproperty.com.my", url_hint="https://www.iproperty.com.my/",
    ),
    AuthorityTarget(
        key="edgeprop", name="EdgeProp coverage or listing", asset_type="media",
        provenance_domain="edgeprop.my", url_hint="https://www.edgeprop.my/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "propertyguru", "iproperty", "facebook")

PROPERTY_PACK = IndustryPack(
    key="property",
    version="1.0.0",
    report_fact_label="Project, pricing and registration information reviewed",
    label="Property & Real Estate",
    subcategories=(
        "developer", "real_estate_agency", "property_management", "co_living",
        "other_property",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(PROPERTY_PACK)
