"""Local services intelligence pack.

Specializes scanning and accuracy triage for trades, home maintenance,
automotive, cleaning, beauty and similar locally delivered services.

The defining risk is a promise about availability or cover. Someone with a
burst pipe at 2am acting on a false "24-hour emergency callout" answer is
stranded at the worst possible moment, and a customer who believes a
tradesperson carries public liability cover when the approved facts do not say
so is exposed financially. Those outrank a wrong price or a wrong opening time.

Service EXCLUSIONS are a first-class fact here: what a trade does not do is as
load-bearing as what it does, because without it an invented service cannot be
told apart from one that simply is not listed yet.

Instructions describe what a reviewer should CHECK. None asserts that anyone is
unlicensed or uninsured — SeenBy reports what an AI system said and cannot
adjudicate who holds a licence.
"""
from app.industry_packs import registry
from app.industry_packs.base import (
    IndustryPack,
    QueryTemplate,
    RiskRule,
    TrustedSourceType,
    TruthFieldDefinition,
)

_TRUTH_FIELDS = (
    # --- services
    TruthFieldDefinition(
        key="catalog", label="Services offered", value_type="list",
        scope="either", fact_type="service", required=True,
    ),
    TruthFieldDefinition(
        key="exclusions", label="Services explicitly not offered", value_type="list",
        scope="either", fact_type="service",
    ),
    TruthFieldDefinition(
        key="specialisations", label="Specialisations", value_type="list",
        scope="either", fact_type="service",
    ),

    # --- coverage
    TruthFieldDefinition(
        key="areas", label="Service areas covered", value_type="list",
        scope="either", fact_type="coverage", required=True, risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="travel_radius_km", label="Travel radius (km)", value_type="number",
        scope="either", fact_type="coverage",
    ),
    TruthFieldDefinition(
        key="callout_fee_applies", label="Callout fee outside base area",
        value_type="boolean", scope="either", fact_type="coverage",
    ),

    # --- availability
    TruthFieldDefinition(
        key="emergency", label="Emergency callout available", value_type="boolean",
        scope="either", fact_type="availability", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="same_day", label="Same-day service available", value_type="boolean",
        scope="either", fact_type="availability", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="response_time", label="Typical response time", value_type="text",
        scope="either", fact_type="availability", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="operating_hours", label="Operating hours", value_type="hours",
        scope="location", fact_type="availability",
    ),

    # --- licensing and insurance: the claims a customer relies on most and can
    # verify least, so both are risk-sensitive.
    TruthFieldDefinition(
        key="held", label="Licences and certifications held", value_type="list",
        scope="either", fact_type="licensing", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="reference_number", label="Licence reference number", value_type="text",
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

    # --- pricing
    TruthFieldDefinition(
        key="model", label="Pricing model", value_type="text",
        scope="either", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="callout_fee", label="Callout fee", value_type="text",
        scope="either", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="free_quote", label="Free quotation offered", value_type="boolean",
        scope="either", fact_type="pricing",
    ),

    # --- warranty and booking
    TruthFieldDefinition(
        key="terms", label="Warranty or guarantee terms", value_type="text",
        scope="either", fact_type="warranty", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="duration", label="Warranty duration", value_type="text",
        scope="either", fact_type="warranty",
    ),
    TruthFieldDefinition(
        key="channel", label="How to book", value_type="text",
        scope="either", fact_type="booking",
    ),
    TruthFieldDefinition(
        key="booking_url", label="Booking URL", value_type="url",
        scope="either", fact_type="booking",
    ),
)

_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    QueryTemplate(
        id="problem_solver", template="Who can fix {problem} in {city}?",
        buyer_stage="awareness", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="service_discovery", template="Who offers {service} in {location}?",
        buyer_stage="awareness", commercial_intent="high", location_required=True,
    ),
    # consideration
    QueryTemplate(
        id="near_me", template="Best {industry} near {area}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="coverage_check", template="Does {brand} cover {area}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="price_check", template="How much does {service} cost in {city}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="trust_check", template="Is {brand} reliable?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="warranty_check", template="Does {brand} guarantee its work?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    # decision
    QueryTemplate(
        id="emergency", template="Emergency {service} in {city} right now",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="same_day", template="Same day {service} in {area}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} or {competitor}: who should I hire?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="booking", template="How do I book {brand}?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_emergency_availability",
        fact_type="availability", fact_key="emergency", severity="critical",
        review_instruction=(
            "An AI answer states emergency or out-of-hours availability the approved "
            "fact does not support. Confirm what callout cover the business actually "
            "offers; someone could rely on this in the middle of the night."
        ),
    ),
    RiskRule(
        id="false_licensing",
        fact_type="licensing", fact_key="held", severity="critical",
        review_instruction=(
            "An AI answer states a licence or certification that differs from the "
            "approved fact. Confirm what the business currently holds, and with which "
            "body, before requesting a correction."
        ),
    ),
    RiskRule(
        id="false_insurance",
        fact_type="insurance", fact_key=None, severity="critical",
        review_instruction=(
            "An AI answer describes insurance cover the approved fact does not "
            "support. Confirm the current cover and its limits; a customer may be "
            "relying on this when deciding who to let into their home."
        ),
    ),
    RiskRule(
        id="wrong_service_area",
        fact_type="coverage", fact_key="areas", severity="high",
        review_instruction=(
            "An AI answer claims coverage of an area the approved fact does not "
            "include. Confirm the current service areas and travel radius."
        ),
    ),
    RiskRule(
        id="false_price_guarantee",
        fact_type="pricing", fact_key=None, severity="high",
        review_instruction=(
            "An AI answer promises pricing or a fixed quote the approved facts do not "
            "support. Confirm the pricing model and whether any figure is guaranteed."
        ),
    ),
    RiskRule(
        id="false_warranty_promise",
        fact_type="warranty", fact_key="terms", severity="high",
        review_instruction=(
            "An AI answer describes a guarantee that differs from the approved fact. "
            "Confirm the actual warranty terms and duration."
        ),
    ),
    RiskRule(
        id="invented_service",
        fact_type="service", fact_key="catalog", severity="high",
        review_instruction=(
            "An AI answer describes a service the approved catalog does not list. "
            "Check the exclusions fact too — a service may be one the business has "
            "deliberately chosen not to take on."
        ),
    ),
    RiskRule(
        id="false_response_time",
        fact_type="availability", fact_key="response_time", severity="medium",
        review_instruction=(
            "An AI answer quotes a response time the approved fact does not support. "
            "Confirm the typical turnaround the business commits to."
        ),
    ),
    RiskRule(
        id="wrong_same_day_availability",
        fact_type="availability", fact_key="same_day", severity="medium",
        review_instruction=(
            "An AI answer states same-day availability that differs from the approved "
            "fact. Confirm current lead times."
        ),
    ),
    RiskRule(
        id="wrong_booking_channel",
        fact_type="booking", fact_key=None, severity="low",
        review_instruction=(
            "An AI answer describes a booking route that differs from the approved "
            "fact. Confirm how the business currently takes work."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="licensing_body", label="Licensing body"),
    TrustedSourceType(key="trade_association", label="Trade association"),
    TrustedSourceType(key="google_business_profile", label="Google Business Profile"),
    TrustedSourceType(key="recognized_directory", label="Recognised trade directory"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

LOCAL_SERVICES_PACK = IndustryPack(
    key="local_services",
    version="1.0.0",
    label="Local Services",
    subcategories=(
        "home_maintenance", "automotive", "beauty_wellness", "cleaning",
        "repair", "professional_local", "emergency_service", "other_local_service",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
)

registry.register(LOCAL_SERVICES_PACK)
