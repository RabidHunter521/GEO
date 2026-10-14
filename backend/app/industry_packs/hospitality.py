"""Hospitality and travel intelligence pack.

For hotels, resorts, homestays and serviced stays, tour operators and event
venues.

A traveller books on the strength of an AI answer and finds out it was wrong
when they arrive, so the defining risks are the claims they cannot easily
verify in advance: a Muslim-friendly or halal kitchen claim, a tourism licence
the operator does not hold, and a cancellation policy that is more generous
than the real one. A wrong room rate costs them less.

Discovery questions are anchored to the occasions, nearby attractions and
destinations the client actually serves (approved facts), because a traveller
asks "where to stay near Legoland for a family trip", not "best hotel".

Instructions describe what a reviewer should CHECK. None asserts that a
business is or is not licensed or certified.
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
    # --- what is offered
    TruthFieldDefinition(
        key="room_types", label="Room or unit types", value_type="list",
        scope="either", fact_type="stay",
    ),
    TruthFieldDefinition(
        key="facilities", label="Facilities (e.g. pool, parking, kids' club)",
        value_type="list", scope="location", fact_type="stay",
    ),
    TruthFieldDefinition(
        key="breakfast_included", label="Breakfast included", value_type="boolean",
        scope="either", fact_type="stay",
    ),
    TruthFieldDefinition(
        key="check_in_out", label="Check-in and check-out times", value_type="text",
        scope="location", fact_type="stay",
    ),
    TruthFieldDefinition(
        key="suitable_for", label="Occasions catered for (e.g. family trips, weddings)",
        value_type="list", scope="either", fact_type="occasion", required=True,
    ),
    TruthFieldDefinition(
        key="attractions", label="Nearby attractions or landmarks", value_type="list",
        scope="location", fact_type="nearby",
    ),

    # --- tours and events
    TruthFieldDefinition(
        key="destinations", label="Tour destinations", value_type="list",
        scope="brand", fact_type="tour",
    ),
    TruthFieldDefinition(
        key="itineraries", label="Tour packages or itineraries", value_type="list",
        scope="brand", fact_type="tour",
    ),
    TruthFieldDefinition(
        key="capacity", label="Event capacity (guests)", value_type="number",
        scope="location", fact_type="venue",
    ),

    # --- pricing and policies
    TruthFieldDefinition(
        key="price_range", label="Price or rate range", value_type="text",
        scope="either", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="cancellation", label="Cancellation policy", value_type="text",
        scope="either", fact_type="policy", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="children", label="Child and extra-bed policy", value_type="text",
        scope="either", fact_type="policy",
    ),

    # --- dietary and licensing: risk-sensitive
    TruthFieldDefinition(
        key="halal_status", label="Halal or Muslim-friendly status", value_type="text",
        scope="either", fact_type="dietary", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="tourism_licence", label="Tourism licence number", value_type="text",
        scope="brand", fact_type="registration", risk_sensitive=True,
    ),
)

# {occasion}, {attraction} and {destination} come from approved facts only.
# {city}-anchored questions land in `local`; {attraction}/{destination}-anchored
# ones in `recommendation`. Both are ranked discovery questions.
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    # consideration
    QueryTemplate(
        id="brand_reviews", template="What do guests say about {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="brand_cancellation", template="What is {brand}'s cancellation policy?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="country_best", template="Which {industry} is the best in {country}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="city_best", template="Best {industry} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="occasion_in_city", template="Where to stay in {city} for {occasion}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="near_attraction", template="Best {industry} near {attraction}",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} vs {competitor}: which is better?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific (at most four each; registry test) ------------
    QueryTemplate(
        id="hotel_business", template="Best business hotel in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("hotel",),
    ),
    QueryTemplate(
        id="hotel_family", template="Family-friendly hotels in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("hotel",),
    ),
    QueryTemplate(
        id="hotel_brand_breakfast", template="Does {brand} include breakfast?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("hotel",),
    ),
    QueryTemplate(
        id="resort_family", template="Best family resort in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("resort",),
    ),
    QueryTemplate(
        id="resort_honeymoon", template="Best resort for a honeymoon in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("resort",),
    ),
    QueryTemplate(
        id="resort_brand_kids", template="Is {brand} good for young children?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("resort",),
    ),
    QueryTemplate(
        id="homestay_big_family", template="Best homestay in {city} for a big family",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("homestay",),
    ),
    QueryTemplate(
        id="homestay_muslim_friendly", template="Muslim-friendly homestay in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("homestay",),
    ),
    QueryTemplate(
        id="homestay_brand_clean", template="Is {brand} clean and safe?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("homestay",),
    ),
    QueryTemplate(
        id="tour_packages", template="Best tour packages to {destination}",
        buyer_stage="decision", commercial_intent="high", location_required=False,
        subcategories=("tour_operator",),
    ),
    QueryTemplate(
        id="tour_day_trips", template="Best day trips from {city}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("tour_operator",),
    ),
    QueryTemplate(
        id="tour_brand_licensed", template="Is {brand} a licensed tour operator?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("tour_operator",),
    ),
    QueryTemplate(
        id="venue_occasion", template="Best venue for {occasion} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("event_venue",),
    ),
    QueryTemplate(
        id="venue_affordable", template="Affordable event halls in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("event_venue",),
    ),
    QueryTemplate(
        id="venue_brand_packages", template="What packages does {brand} offer?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("event_venue",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="wrong_halal_status",
        fact_type="dietary", fact_key="halal_status", severity="critical",
        review_instruction=(
            "An AI answer states a halal or Muslim-friendly status that differs from "
            "the approved fact. Check the current certification record before "
            "responding; a guest may book on the strength of that answer."
        ),
    ),
    RiskRule(
        id="wrong_tourism_licence",
        fact_type="registration", fact_key="tourism_licence", severity="critical",
        review_instruction=(
            "An AI answer states a tourism licence that differs from the approved "
            "fact. Check the tourism ministry's register before responding."
        ),
    ),
    RiskRule(
        id="wrong_cancellation_policy",
        fact_type="policy", fact_key="cancellation", severity="high",
        review_instruction=(
            "An AI answer describes a cancellation policy that differs from the "
            "approved fact. Confirm the current terms; a guest could book expecting "
            "a refund they will not get."
        ),
    ),
    RiskRule(
        id="invented_facility",
        fact_type="stay", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes rooms, facilities or inclusions the approved facts "
            "do not list. Confirm what the property offers."
        ),
    ),
    RiskRule(
        id="wrong_price",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes rates that differ from the approved fact. Confirm the "
            "current price range."
        ),
    ),
    RiskRule(
        id="wrong_capacity",
        fact_type="venue", fact_key="capacity", severity="medium",
        review_instruction=(
            "An AI answer states an event capacity that differs from the approved "
            "fact. Confirm how many guests the venue holds."
        ),
    ),
    RiskRule(
        id="invented_tour",
        fact_type="tour", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes a tour or destination the approved facts do not "
            "list. Confirm which packages the operator runs."
        ),
    ),
    RiskRule(
        id="wrong_child_policy",
        fact_type="policy", fact_key="children", severity="low",
        review_instruction=(
            "An AI answer describes a child or extra-bed policy that differs from the "
            "approved fact. Confirm the current policy."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="tourism_register", label="Tourism licence register"),
    TrustedSourceType(key="certification_body", label="Certifying body's listing"),
    TrustedSourceType(key="booking_platform", label="Online travel agency listing"),
    TrustedSourceType(key="review_platform", label="Review platform"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

_SCHEMA = SchemaProfile(
    default_type="LodgingBusiness",
    subcategory_types=(
        ("hotel", "Hotel"),
        ("resort", "Resort"),
        ("tour_operator", "TravelAgency"),
        ("event_venue", "EventVenue"),
    ),
    guidance=(
        "Add `amenityFeature` only for facilities the description names.",
        "Do not emit room rates, prices or offers; they change too often to "
        "publish on the client's own site.",
        "Do not emit halal, licence or cancellation-policy claims. Those are "
        "risk-sensitive facts requiring an approved source.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="agoda", name="Agoda listing", asset_type="directory",
        provenance_domain="agoda.com", url_hint="https://www.agoda.com/",
    ),
    AuthorityTarget(
        key="booking_com", name="Booking.com listing", asset_type="directory",
        provenance_domain="booking.com", url_hint="https://www.booking.com/",
    ),
    AuthorityTarget(
        key="klook", name="Klook listing", asset_type="directory",
        provenance_domain="klook.com", url_hint="https://www.klook.com/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "booking_com", "agoda", "instagram")

HOSPITALITY_PACK = IndustryPack(
    key="hospitality",
    version="1.0.0",
    report_fact_label="Stay, policy and licensing information reviewed",
    label="Hospitality & Travel",
    subcategories=(
        "hotel", "resort", "homestay", "tour_operator", "event_venue",
        "other_hospitality",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(HOSPITALITY_PACK)
