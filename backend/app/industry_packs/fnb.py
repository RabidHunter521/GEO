"""Food & beverage intelligence pack.

Specializes scanning and accuracy triage for restaurants, cafes, bakeries, bars
and delivery-first operators.

The defining risk is dietary and religious rather than clinical. A wrong price
irritates a diner; a wrong halal status or a missed allergen can make food
unacceptable or unsafe for the person eating it, and no amount of later
correction undoes that. Halal and allergen facts are therefore risk-sensitive —
they require an approved fact and a source before any surface repeats them —
and their conflicts are triaged at the top.

As everywhere in this system, instructions tell a reviewer what to CHECK.
SeenBy observes what AI systems say about a venue; it does not certify anyone.
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
    # --- outlets
    TruthFieldDefinition(
        key="name", label="Outlet name", value_type="text",
        scope="location", fact_type="outlet", required=True,
    ),
    TruthFieldDefinition(
        key="seating_capacity", label="Seating capacity", value_type="number",
        scope="location", fact_type="outlet",
    ),
    TruthFieldDefinition(
        key="dine_in_available", label="Dine-in available", value_type="boolean",
        scope="location", fact_type="outlet",
    ),

    # --- hours: kitchen hours are tracked separately because a kitchen that
    # closes before the venue is the most common cause of a wrong "are they
    # open" answer, and the two conflict independently.
    TruthFieldDefinition(
        key="operating", label="Operating hours", value_type="hours",
        scope="location", fact_type="hours", required=True,
    ),
    TruthFieldDefinition(
        key="kitchen", label="Kitchen hours", value_type="hours",
        scope="location", fact_type="hours",
    ),
    TruthFieldDefinition(
        key="last_order", label="Last order time", value_type="text",
        scope="location", fact_type="hours",
    ),

    # --- menu
    TruthFieldDefinition(
        key="signature_dishes", label="Signature dishes", value_type="list",
        scope="either", fact_type="menu", required=True,
    ),
    TruthFieldDefinition(
        key="items", label="Menu items", value_type="list",
        scope="either", fact_type="menu",
    ),
    TruthFieldDefinition(
        key="menu_url", label="Menu URL", value_type="url",
        scope="either", fact_type="menu",
    ),

    # --- cuisine
    TruthFieldDefinition(
        key="types", label="Cuisine types", value_type="list",
        scope="either", fact_type="cuisine", required=True,
    ),

    # --- dietary: every one of these is risk-sensitive
    TruthFieldDefinition(
        key="halal_status", label="Halal status", value_type="text",
        scope="either", fact_type="dietary", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="halal_certifier", label="Halal certifying body", value_type="text",
        scope="either", fact_type="dietary", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="options", label="Dietary options offered", value_type="list",
        scope="either", fact_type="dietary", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="allergens", label="Allergen information", value_type="list",
        scope="either", fact_type="dietary", risk_sensitive=True,
    ),

    # --- pricing
    TruthFieldDefinition(
        key="price_range", label="Price range", value_type="text",
        scope="either", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="set_menu_price", label="Set menu price", value_type="text",
        scope="either", fact_type="pricing",
    ),

    # --- reservation and delivery
    TruthFieldDefinition(
        key="accepted", label="Reservations accepted", value_type="boolean",
        scope="either", fact_type="reservation",
    ),
    TruthFieldDefinition(
        key="booking_url", label="Booking URL", value_type="url",
        scope="either", fact_type="reservation",
    ),
    TruthFieldDefinition(
        key="available", label="Delivery available", value_type="boolean",
        scope="either", fact_type="delivery",
    ),
    TruthFieldDefinition(
        key="platforms", label="Delivery platforms", value_type="list",
        scope="either", fact_type="delivery",
    ),

    # --- facilities and occasions
    TruthFieldDefinition(
        key="amenities", label="Facilities", value_type="list",
        scope="location", fact_type="facility",
    ),
    TruthFieldDefinition(
        key="suitable_for", label="Occasions catered for", value_type="list",
        scope="either", fact_type="occasion",
    ),
)

_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    QueryTemplate(
        id="dish_discovery", template="Where can I get good {dish} in {city}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
    ),
    QueryTemplate(
        id="cuisine_discovery", template="Best {cuisine} restaurants in {location}",
        buyer_stage="awareness", commercial_intent="high", location_required=True,
    ),
    # consideration
    QueryTemplate(
        id="occasion", template="Where should I go for {occasion} in {city}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="dietary_requirement",
        template="Which restaurants in {city} have {dietary} options?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="brand_menu", template="What is on the menu at {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="price_check", template="How expensive is {brand}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="brand_dietary", template="Is {brand} halal?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    # decision
    QueryTemplate(
        id="local_best", template="Best {industry} in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} or {competitor}: where should I eat?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="delivery_available", template="Does {brand} deliver?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="booking", template="How do I book a table at {brand}?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="late_night", template="What food is open late in {area}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_halal_claim",
        fact_type="dietary", fact_key="halal_status", severity="critical",
        review_instruction=(
            "An AI answer states a halal status that differs from the approved fact. "
            "Check the venue's current certification record and its certifying body, "
            "then request a correction. Someone may choose this venue on the strength "
            "of that answer."
        ),
    ),
    RiskRule(
        id="wrong_halal_certifier",
        fact_type="dietary", fact_key="halal_certifier", severity="high",
        review_instruction=(
            "An AI answer names a certifying body that differs from the approved "
            "fact. Confirm which body issued the venue's current certification."
        ),
    ),
    RiskRule(
        id="wrong_allergen_information",
        fact_type="dietary", fact_key="allergens", severity="critical",
        review_instruction=(
            "An AI answer states allergen information that differs from the approved "
            "fact. Confirm against the venue's own allergen record before responding; "
            "a diner could act on this when choosing what to eat."
        ),
    ),
    RiskRule(
        id="wrong_dietary_options",
        fact_type="dietary", fact_key="options", severity="high",
        review_instruction=(
            "An AI answer lists dietary options the approved fact does not include. "
            "Confirm what the venue actually offers."
        ),
    ),
    RiskRule(
        id="invented_menu_item",
        fact_type="menu", fact_key=None, severity="high",
        review_instruction=(
            "An AI answer describes a dish the approved menu facts do not list. "
            "Confirm whether the venue serves it; a diner could arrive expecting it."
        ),
    ),
    RiskRule(
        id="wrong_cuisine",
        fact_type="cuisine", fact_key="types", severity="medium",
        review_instruction=(
            "An AI answer describes a cuisine the approved fact does not list. "
            "Confirm how the venue describes its own cuisine."
        ),
    ),
    RiskRule(
        id="wrong_price",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes pricing that differs from the approved fact. "
            "Confirm the current price range or set menu price."
        ),
    ),
    RiskRule(
        id="wrong_operating_hours",
        fact_type="hours", fact_key="operating", severity="medium",
        review_instruction=(
            "An AI answer states operating hours that differ from the approved fact. "
            "Confirm the current hours, including any seasonal variation."
        ),
    ),
    RiskRule(
        id="wrong_kitchen_hours",
        fact_type="hours", fact_key="kitchen", severity="medium",
        review_instruction=(
            "An AI answer states kitchen or last-order times that differ from the "
            "approved fact. Confirm when the kitchen actually stops serving."
        ),
    ),
    RiskRule(
        id="wrong_outlet_detail",
        fact_type="outlet", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes an outlet in a way the approved facts do not "
            "support. Confirm which outlets exist and what each offers."
        ),
    ),
    RiskRule(
        id="wrong_reservation_policy",
        fact_type="reservation", fact_key="accepted", severity="low",
        review_instruction=(
            "An AI answer describes a reservation policy that differs from the "
            "approved fact. Confirm whether the venue takes bookings."
        ),
    ),
    RiskRule(
        id="wrong_delivery_availability",
        fact_type="delivery", fact_key=None, severity="low",
        review_instruction=(
            "An AI answer describes delivery availability or platforms that differ "
            "from the approved fact. Confirm the current arrangements."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="certification_body", label="Certification body"),
    TrustedSourceType(key="google_business_profile", label="Google Business Profile"),
    TrustedSourceType(key="delivery_platform", label="Delivery platform listing"),
    TrustedSourceType(key="reservation_platform", label="Reservation platform listing"),
    TrustedSourceType(key="recognized_directory", label="Recognised food directory"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

# `catering`, `food_delivery` and `other_fnb` deliberately have no override:
# schema.org has no type that fits them better than FoodEstablishment, and
# inventing a closer-sounding one would put an invalid @type on a client's site.
_SCHEMA = SchemaProfile(
    default_type="FoodEstablishment",
    subcategory_types=(
        ("restaurant", "Restaurant"),
        ("cafe", "CafeOrCoffeeShop"),
        ("bakery", "Bakery"),
        ("bar", "BarOrPub"),
        ("quick_service", "FastFoodRestaurant"),
    ),
    guidance=(
        "Add `servesCuisine` only when the description names the cuisine "
        "outright.",
        "Add `hasMenu` only with a real menu URL on the business's own domain. "
        "Never invent a menu path, and never inline menu items or prices.",
        "Do not emit halal, vegetarian, vegan, allergen or any other dietary "
        "property. Those are risk-sensitive facts requiring an approved source, "
        "and wrong dietary markup is the most harmful error this file can carry.",
        "Add `acceptsReservations` only when the description states it.",
    ),
)

# Delivery marketplaces are listed as directories: they are where a buyer finds
# the outlet, which is what the authority checklist tracks. The catalog already
# carries the platform-neutral entries (GBP, Facebook, Instagram).
_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="tripadvisor", name="TripAdvisor listing", asset_type="review_platform",
        provenance_domain="tripadvisor.com", url_hint="https://www.tripadvisor.com/",
    ),
    AuthorityTarget(
        key="foodpanda", name="Foodpanda merchant listing", asset_type="directory",
        provenance_domain="foodpanda.my", url_hint="https://www.foodpanda.my/",
    ),
    AuthorityTarget(
        key="grabfood", name="GrabFood merchant listing", asset_type="directory",
        provenance_domain="grab.com", url_hint="https://food.grab.com/my/en/",
    ),
    AuthorityTarget(
        key="burpple", name="Burpple listing", asset_type="review_platform",
        provenance_domain="burpple.com", url_hint="https://www.burpple.com/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "tripadvisor", "foodpanda", "instagram")

FNB_PACK = IndustryPack(
    key="fnb",
    version="1.0.0",
    report_fact_label="Outlet, menu and dietary information reviewed",
    label="Food & Beverage",
    subcategories=(
        "restaurant", "cafe", "bakery", "bar", "catering",
        "food_delivery", "quick_service", "other_fnb",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(FNB_PACK)
