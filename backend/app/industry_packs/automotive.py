"""Automotive sales intelligence pack.

For new and used car dealers, EV showrooms, motorcycle dealers and car rental.
Repair and servicing workshops stay in the Local Services pack.

A buyer hands over a deposit on the strength of an AI answer, so the defining
risks are claims about who stands behind the car: an authorised-dealer status
the business does not hold, a warranty or used-car inspection programme it does
not offer, or a licence it does not have. A wrong price is corrected at the
showroom; a wrong authorisation is not.

Discovery questions are anchored to the makes, models and vehicle types the
client actually sells (approved facts), because a buyer asks "where to buy a
used Honda City in Shah Alam", not "best car dealer".

Instructions describe what a reviewer should CHECK. None asserts that a
dealer is or is not authorised or licensed.
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
        key="makes", label="Makes sold (e.g. Honda, Proton, BYD)", value_type="list",
        scope="either", fact_type="vehicle", required=True,
    ),
    TruthFieldDefinition(
        key="models", label="Models sold", value_type="list",
        scope="either", fact_type="vehicle",
    ),
    TruthFieldDefinition(
        key="types", label="Vehicle types (e.g. SUV, MPV, EV, motorcycle)",
        value_type="list", scope="either", fact_type="vehicle",
    ),
    TruthFieldDefinition(
        key="catalog", label="Services offered (e.g. servicing, insurance renewal)",
        value_type="list", scope="either", fact_type="service",
    ),

    # --- pricing and finance
    TruthFieldDefinition(
        key="price_range", label="Price range", value_type="text",
        scope="either", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="loan_partners", label="Loan partner banks", value_type="list",
        scope="either", fact_type="finance",
    ),
    TruthFieldDefinition(
        key="trade_in", label="Trade-in accepted", value_type="boolean",
        scope="either", fact_type="finance",
    ),

    # --- who stands behind the car: risk-sensitive
    TruthFieldDefinition(
        key="authorised_for", label="Makes it is an authorised dealer for",
        value_type="list", scope="either", fact_type="dealer", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="terms", label="Warranty terms", value_type="text",
        scope="either", fact_type="warranty", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="programme", label="Used-car inspection or certification programme",
        value_type="text", scope="either", fact_type="inspection", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="held", label="Licences held", value_type="list",
        scope="either", fact_type="licensing", risk_sensitive=True,
    ),
)

# {make}, {model} and {vehicle_type} come from approved vehicle facts only.
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
        id="model_price", template="How much is a {model} in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="country_best", template="Which {industry} is the best in {country}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="buy_make_in_city", template="Where to buy a {make} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="best_make_dealer", template="Best {make} dealer in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} vs {competitor}: which is better?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific (at most four each; registry test) ------------
    QueryTemplate(
        id="new_showroom", template="Best {make} showroom in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("new_car_dealer",),
    ),
    QueryTemplate(
        id="new_brand_authorised", template="Is {brand} an authorised {make} dealer?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("new_car_dealer",),
    ),
    QueryTemplate(
        id="used_reliable", template="Where to buy a reliable used car in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("used_car_dealer",),
    ),
    QueryTemplate(
        id="used_type_in_city", template="Where to buy a used {vehicle_type} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("used_car_dealer",),
    ),
    QueryTemplate(
        id="used_brand_warranty", template="Does {brand} offer a warranty on used cars?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("used_car_dealer",),
    ),
    QueryTemplate(
        id="ev_where_to_buy", template="Where to buy an electric car in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("ev_dealer",),
    ),
    QueryTemplate(
        id="ev_best_showroom", template="Best EV showroom in {location}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("ev_dealer",),
    ),
    QueryTemplate(
        id="ev_brand_charger", template="Does {brand} install home chargers?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("ev_dealer",),
    ),
    QueryTemplate(
        id="moto_best_shop", template="Best motorcycle shop in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("motorcycle_dealer",),
    ),
    QueryTemplate(
        id="moto_make_in_city", template="Where to buy a {make} motorcycle in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("motorcycle_dealer",),
    ),
    QueryTemplate(
        id="rental_best", template="Best car rental in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("car_rental",),
    ),
    QueryTemplate(
        id="rental_airport", template="Cheap car rental at {city} airport",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("car_rental",),
    ),
    QueryTemplate(
        id="rental_brand_deposit", template="Does {brand} require a deposit?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("car_rental",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_authorised_dealer",
        fact_type="dealer", fact_key="authorised_for", severity="critical",
        review_instruction=(
            "An AI answer says the business is an authorised dealer for a make the "
            "approved fact does not list. Check the manufacturer's dealer list before "
            "responding; a buyer may pay a deposit on the strength of that answer."
        ),
    ),
    RiskRule(
        id="wrong_licence",
        fact_type="licensing", fact_key="held", severity="high",
        review_instruction=(
            "An AI answer states a licence that differs from the approved fact. Check "
            "the relevant register before responding."
        ),
    ),
    RiskRule(
        id="wrong_warranty",
        fact_type="warranty", fact_key="terms", severity="high",
        review_instruction=(
            "An AI answer describes warranty terms that differ from the approved fact. "
            "Confirm what the warranty covers and for how long."
        ),
    ),
    RiskRule(
        id="wrong_inspection_claim",
        fact_type="inspection", fact_key="programme", severity="high",
        review_instruction=(
            "An AI answer describes a used-car inspection or certification programme "
            "that differs from the approved fact. Confirm what checks are actually done."
        ),
    ),
    RiskRule(
        id="invented_vehicle",
        fact_type="vehicle", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer says the business sells a make, model or vehicle type the "
            "approved facts do not list. Confirm what is sold."
        ),
    ),
    RiskRule(
        id="wrong_price",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes prices that differ from the approved fact. Confirm the "
            "current price range."
        ),
    ),
    RiskRule(
        id="wrong_finance_detail",
        fact_type="finance", fact_key=None, severity="low",
        review_instruction=(
            "An AI answer describes loan partners or trade-in terms that differ from the "
            "approved facts. Confirm the current arrangements."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="manufacturer_dealer_list", label="Manufacturer's authorised dealer list"),
    TrustedSourceType(key="company_registry", label="Company registry (e.g. SSM)"),
    TrustedSourceType(key="car_marketplace", label="Car marketplace listing"),
    TrustedSourceType(key="consumer_review_site", label="Consumer review site"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

_SCHEMA = SchemaProfile(
    default_type="AutoDealer",
    subcategory_types=(
        ("motorcycle_dealer", "MotorcycleDealer"),
        ("car_rental", "AutoRental"),
    ),
    guidance=(
        "Add `brand` only for makes the description says the dealer sells.",
        "Do not emit prices, promotions or loan rates; they change too often.",
        "Do not emit authorised-dealer, warranty, inspection or licence claims. "
        "Those are risk-sensitive facts requiring an approved source.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="carlist", name="Carlist.my listing", asset_type="directory",
        provenance_domain="carlist.my", url_hint="https://www.carlist.my/",
    ),
    AuthorityTarget(
        key="carsome", name="Carsome listing", asset_type="directory",
        provenance_domain="carsome.my", url_hint="https://www.carsome.my/",
    ),
    AuthorityTarget(
        key="paultan", name="Paul Tan's Automotive News coverage", asset_type="media",
        provenance_domain="paultan.org", url_hint="https://paultan.org/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "carlist", "facebook", "paultan")

AUTOMOTIVE_PACK = IndustryPack(
    key="automotive",
    version="1.0.0",
    report_fact_label="Vehicle, dealer and warranty information reviewed",
    label="Automotive Sales",
    subcategories=(
        "new_car_dealer", "used_car_dealer", "ev_dealer", "motorcycle_dealer",
        "car_rental", "other_automotive",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(AUTOMOTIVE_PACK)
