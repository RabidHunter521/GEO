"""B2B and online services intelligence pack.

For businesses that sell to other businesses across a whole country rather
than to walk-in customers near one address: payment gateways, business
software, SME financing, professional firms and logistics partners.

The four older packs ask local-shop questions ("best X near me in {city}",
"signs I need an X"). A merchant choosing a payment gateway asks which one has
the lowest fees in Malaysia, which works with their Shopify store and which
handles recurring billing, so this pack's discovery questions are pinned to
the client's {country} and to the approved facts that make a provider fit a
buyer (services, integrations), not to a street address.

The defining risk is a claim a buyer relies on when handing over money or
customer data: a licence or regulatory approval the business does not hold, a
security certification it does not have, or a payment method it does not
support. Those outrank a wrong price.

Instructions describe what a reviewer should CHECK. None asserts that a
business is or is not authorised -- SeenBy reports what an AI system said and
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
    # --- what is sold
    TruthFieldDefinition(
        key="catalog", label="Products or services offered", value_type="list",
        scope="brand", fact_type="service", required=True,
    ),
    TruthFieldDefinition(
        key="specialisations", label="Specialisations", value_type="list",
        scope="brand", fact_type="service",
    ),
    TruthFieldDefinition(
        key="exclusions", label="Products or services explicitly not offered",
        value_type="list", scope="brand", fact_type="service",
    ),

    # --- who it is sold to
    TruthFieldDefinition(
        key="countries", label="Countries served", value_type="list",
        scope="brand", fact_type="market", required=True,
    ),
    TruthFieldDefinition(
        key="customer_segments", label="Customer segments served", value_type="list",
        scope="brand", fact_type="market",
    ),

    # --- pricing
    TruthFieldDefinition(
        key="model", label="Pricing model", value_type="text",
        scope="brand", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="published_rates", label="Published fees or rates", value_type="text",
        scope="brand", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="setup_fee", label="Setup fee", value_type="text",
        scope="brand", fact_type="pricing",
    ),

    # --- integrations
    TruthFieldDefinition(
        key="platforms", label="Platforms it integrates with", value_type="list",
        scope="brand", fact_type="integration",
    ),
    TruthFieldDefinition(
        key="api_available", label="Public API available", value_type="boolean",
        scope="brand", fact_type="integration",
    ),

    # --- payments (payment gateways, financing)
    TruthFieldDefinition(
        key="methods_supported", label="Payment methods supported", value_type="list",
        scope="brand", fact_type="payment", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="settlement_time", label="Typical settlement time", value_type="text",
        scope="brand", fact_type="payment", risk_sensitive=True,
    ),

    # --- regulatory and security: every one of these is risk-sensitive
    TruthFieldDefinition(
        key="licences", label="Licences and regulatory approvals held",
        value_type="list", scope="brand", fact_type="regulatory", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="regulator", label="Regulator", value_type="text",
        scope="brand", fact_type="regulatory", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="certifications", label="Security certifications (e.g. PCI DSS)",
        value_type="list", scope="brand", fact_type="security", risk_sensitive=True,
    ),

    # --- support and onboarding
    TruthFieldDefinition(
        key="channels", label="Support channels", value_type="list",
        scope="brand", fact_type="support",
    ),
    TruthFieldDefinition(
        key="hours", label="Support hours", value_type="text",
        scope="brand", fact_type="support",
    ),
    TruthFieldDefinition(
        key="time", label="Typical onboarding time", value_type="text",
        scope="brand", fact_type="onboarding",
    ),

    # --- company identity
    TruthFieldDefinition(
        key="parent", label="Parent company", value_type="text",
        scope="brand", fact_type="company",
    ),
    TruthFieldDefinition(
        key="founded", label="Year founded", value_type="text",
        scope="brand", fact_type="company",
    ),
)

# Discovery questions are buyer-neutral and pinned to {country}: they never
# name the brand, so a "seen" there is earned, not echoed back. {brand}
# questions are knowledge and accuracy checks and land in `brand`, which is not
# ranked. {country}-only questions land in `recommendation`, which IS ranked --
# correct, they are shortlist questions worth the position-extraction call.
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    QueryTemplate(
        id="how_to_choose",
        template="How do businesses in {country} choose a {industry}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
    ),
    # consideration
    QueryTemplate(
        id="most_used", template="Which {industry} do businesses in {country} use most?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="most_trusted", template="What is the most trusted {industry} in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="for_enterprise", template="Best {industry} for large companies in {country}",
        buyer_stage="consideration", commercial_intent="medium", location_required=True,
    ),
    QueryTemplate(
        id="brand_pricing", template="How much does {brand} cost?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="brand_reviews", template="What do businesses say about {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    # decision
    QueryTemplate(
        id="for_smb", template="Best {industry} for small businesses in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="lowest_fees", template="Which {industry} in {country} has the lowest fees?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="service_best", template="Best {service} provider in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="city_top", template="Top {industry} companies in {city}",
        buyer_stage="decision", commercial_intent="medium", location_required=True,
    ),
    QueryTemplate(
        id="brand_vs_competitor",
        template="{brand} vs {competitor}: which is better for a business in {country}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),

    # --- subcategory-specific -------------------------------------------------
    # At most four per subcategory (registry test): payment gateways spend
    # theirs on discovery questions, which are what the score measures.
    QueryTemplate(
        id="pg_online_store",
        template="Best payment gateway for an online store in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("payment_gateway",),
    ),
    QueryTemplate(
        id="pg_integration",
        template="Best payment gateway for {integration} in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("payment_gateway",),
    ),
    QueryTemplate(
        id="pg_recurring",
        template="Best payment gateway for subscriptions and recurring billing in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("payment_gateway",),
    ),
    QueryTemplate(
        id="pg_local_methods",
        template="Which payment gateway in {country} supports local online banking and e-wallets?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("payment_gateway",),
    ),
    QueryTemplate(
        id="sw_for_smb",
        template="Best {service} software for small businesses in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("business_software",),
    ),
    QueryTemplate(
        id="sw_brand_integrations", template="What does {brand} integrate with?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("business_software",),
    ),
    QueryTemplate(
        id="fl_sme_financing",
        template="Where can an SME in {country} get business financing quickly?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("sme_financing",),
    ),
    QueryTemplate(
        id="fl_brand_requirements",
        template="What do I need to apply for financing with {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("sme_financing",),
    ),
    QueryTemplate(
        id="ps_for_smes", template="Best {service} firm for SMEs in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("professional_services",),
    ),
    QueryTemplate(
        id="ps_brand_pricing", template="How does {brand} charge for its work?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("professional_services",),
    ),
    QueryTemplate(
        id="lg_for_ecommerce",
        template="Best delivery partner for e-commerce sellers in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("logistics",),
    ),
    QueryTemplate(
        id="lg_brand_coverage", template="Which areas does {brand} deliver to?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("logistics",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_licence_claim",
        fact_type="regulatory", fact_key="licences", severity="critical",
        review_instruction=(
            "An AI answer states a licence or regulatory approval that differs from "
            "the approved fact. Check the regulator's public register before "
            "responding; a business may hand over money or customer data on the "
            "strength of that answer."
        ),
    ),
    RiskRule(
        id="wrong_regulator",
        fact_type="regulatory", fact_key="regulator", severity="high",
        review_instruction=(
            "An AI answer names a regulator that differs from the approved fact. "
            "Confirm which authority the business is registered with."
        ),
    ),
    RiskRule(
        id="false_security_certification",
        fact_type="security", fact_key="certifications", severity="critical",
        review_instruction=(
            "An AI answer states a security certification that differs from the "
            "approved fact. Confirm against the current certificate or the "
            "certifying body's listing before responding."
        ),
    ),
    RiskRule(
        id="wrong_payment_methods",
        fact_type="payment", fact_key="methods_supported", severity="high",
        review_instruction=(
            "An AI answer lists payment methods the approved fact does not include. "
            "Confirm what the business supports today; a merchant could sign up "
            "expecting a method their customers need."
        ),
    ),
    RiskRule(
        id="wrong_settlement_time",
        fact_type="payment", fact_key="settlement_time", severity="medium",
        review_instruction=(
            "An AI answer states a settlement time that differs from the approved "
            "fact. Confirm the current settlement terms."
        ),
    ),
    RiskRule(
        id="invented_service",
        fact_type="service", fact_key=None, severity="high",
        review_instruction=(
            "An AI answer describes a product or service the approved facts do not "
            "list. Confirm whether the business offers it."
        ),
    ),
    RiskRule(
        id="wrong_pricing",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes fees or pricing that differ from the approved fact. "
            "Confirm the current published rates."
        ),
    ),
    RiskRule(
        id="wrong_integration",
        fact_type="integration", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes an integration the approved facts do not list. "
            "Confirm which platforms the business integrates with."
        ),
    ),
    RiskRule(
        id="wrong_market",
        fact_type="market", fact_key="countries", severity="medium",
        review_instruction=(
            "An AI answer says the business serves a country the approved fact does "
            "not list, or not one it does. Confirm where it operates."
        ),
    ),
    RiskRule(
        id="wrong_parent_company",
        fact_type="company", fact_key="parent", severity="low",
        review_instruction=(
            "An AI answer names a parent company that differs from the approved "
            "fact. Confirm the current ownership."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="regulator_register", label="Regulator's public register"),
    TrustedSourceType(key="business_registry", label="Company registry (e.g. SSM)"),
    TrustedSourceType(key="certification_listing", label="Certifying body's listing"),
    TrustedSourceType(key="partner_marketplace", label="Partner app marketplace listing"),
    TrustedSourceType(key="software_review_site", label="Business software review site"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

# Most of these businesses have no customer-facing premises, so the default is
# Organization rather than a LocalBusiness subtype. ProfessionalService is the
# exception: firms do receive clients at an office.
_SCHEMA = SchemaProfile(
    default_type="Organization",
    subcategory_types=(
        ("professional_services", "ProfessionalService"),
    ),
    guidance=(
        "Prefer `areaServed` with the countries the description names over a "
        "street address; omit `address` unless the description gives one.",
        "Add `sameAs` only for official profiles on the business's own accounts "
        "(LinkedIn, Crunchbase); never invent a profile URL.",
        "Do not emit licence, regulator or security certification claims. Those "
        "are risk-sensitive facts requiring an approved source.",
        "Do not emit fees, rates or prices.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="g2", name="G2 profile", asset_type="review_platform",
        provenance_domain="g2.com", url_hint="https://www.g2.com/",
    ),
    AuthorityTarget(
        key="capterra", name="Capterra listing", asset_type="review_platform",
        provenance_domain="capterra.com", url_hint="https://www.capterra.com/",
    ),
    AuthorityTarget(
        key="shopify_app_store", name="Shopify App Store listing", asset_type="directory",
        provenance_domain="apps.shopify.com", url_hint="https://apps.shopify.com/",
    ),
)

_PRIORITY_ASSETS = ("linkedin", "crunchbase", "g2", "trustpilot")

B2B_SERVICES_PACK = IndustryPack(
    key="b2b_services",
    version="1.0.0",
    report_fact_label="Product, pricing and regulatory information reviewed",
    label="B2B & Online Services",
    subcategories=(
        "payment_gateway", "business_software", "sme_financing",
        "professional_services", "logistics", "other_b2b",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(B2B_SERVICES_PACK)
