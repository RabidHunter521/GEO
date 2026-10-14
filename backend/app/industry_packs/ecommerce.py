"""Retail and e-commerce intelligence pack.

For brands and shops whose buyers ask about PRODUCTS, not services: direct-to-
consumer brands, marketplace sellers (Shopee, Lazada, TikTok Shop), multi-brand
online retailers and physical stores.

A shopper's questions name the product ("best halal skincare brands in
Malaysia", "where to buy running shoes online"), so discovery questions are
built from approved `product.categories` / `product.hero_products` facts.
"Is {brand} legit?" is the single most common brand question for online
shops, so it is asked of every client.

The defining risks are claims a shopper relies on at checkout: a certification
the product does not carry (halal, product notification, safety marks), a
return or warranty policy the shop does not offer. Those outrank a wrong
price.

Instructions describe what a reviewer should CHECK. None asserts that a
product is or is not certified -- SeenBy reports what an AI system said.
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
        key="categories", label="Product categories sold", value_type="list",
        scope="brand", fact_type="product", required=True,
    ),
    TruthFieldDefinition(
        key="hero_products", label="Best-selling or hero products", value_type="list",
        scope="brand", fact_type="product",
    ),
    TruthFieldDefinition(
        key="certifications",
        label="Product certifications (e.g. halal, product notification, SIRIM)",
        value_type="list", scope="brand", fact_type="product", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="origin", label="Where the brand is from or made", value_type="text",
        scope="brand", fact_type="product",
    ),

    # --- where it is sold
    TruthFieldDefinition(
        key="marketplaces", label="Marketplaces sold on (e.g. Shopee, Lazada, TikTok Shop)",
        value_type="list", scope="brand", fact_type="channel",
    ),
    TruthFieldDefinition(
        key="outlets", label="Physical stores", value_type="list",
        scope="location", fact_type="channel",
    ),

    # --- price and checkout
    TruthFieldDefinition(
        key="price_range", label="Price range", value_type="text",
        scope="brand", fact_type="pricing", required=True,
    ),
    TruthFieldDefinition(
        key="payment_methods", label="Payment methods accepted", value_type="list",
        scope="brand", fact_type="checkout",
    ),

    # --- delivery
    TruthFieldDefinition(
        key="areas", label="Shipping coverage", value_type="list",
        scope="brand", fact_type="shipping",
    ),
    TruthFieldDefinition(
        key="free_threshold", label="Free shipping threshold", value_type="text",
        scope="brand", fact_type="shipping",
    ),
    TruthFieldDefinition(
        key="delivery_time", label="Typical delivery time", value_type="text",
        scope="brand", fact_type="shipping",
    ),

    # --- after-sales: risk-sensitive, a shopper relies on them when buying
    TruthFieldDefinition(
        key="policy", label="Return and refund policy", value_type="text",
        scope="brand", fact_type="returns", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="terms", label="Warranty terms", value_type="text",
        scope="brand", fact_type="warranty", risk_sensitive=True,
    ),
)

# {product} and {marketplace} come from approved facts only, so a shop is never
# asked about a product it does not sell. {product}-anchored questions without
# a brand land in `recommendation` (ranked) -- they are shortlist questions.
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    # consideration
    QueryTemplate(
        id="brand_legit", template="Is {brand} legit?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="brand_reviews", template="What do customers say about {brand}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
    ),
    QueryTemplate(
        id="product_affordable", template="Affordable {product} in {country}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="product_best_brands", template="Best {product} brands in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="product_buy_online", template="Where can I buy {product} online in {country}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="product_local_shop", template="Where to buy {product} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="brand_vs_competitor", template="{brand} vs {competitor}: which is better?",
        buyer_stage="decision", commercial_intent="high", location_required=False,
    ),

    # --- subcategory-specific (at most four each; registry test) ------------
    QueryTemplate(
        id="dtc_local_brands", template="Best local {product} brands in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("dtc_brand",),
    ),
    QueryTemplate(
        id="dtc_free_shipping",
        template="{product} brands with free shipping in {country}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("dtc_brand",),
    ),
    QueryTemplate(
        id="dtc_brand_worth_it", template="Is {brand} worth the price?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("dtc_brand",),
    ),
    QueryTemplate(
        id="mkt_best_shops", template="Best {product} shops on {marketplace}",
        buyer_stage="decision", commercial_intent="high", location_required=False,
        subcategories=("marketplace_seller",),
    ),
    QueryTemplate(
        id="mkt_brand_trusted", template="Is {brand} a trusted seller on {marketplace}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("marketplace_seller",),
    ),
    QueryTemplate(
        id="retailer_best_store", template="Best online store for {product} in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("multi_brand_retailer",),
    ),
    QueryTemplate(
        id="retailer_brand_authentic", template="Does {brand} sell authentic products?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("multi_brand_retailer",),
    ),
    QueryTemplate(
        id="store_best_in_city", template="Best {product} store in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("physical_retail",),
    ),
    QueryTemplate(
        id="store_brand_nearest", template="Where is the nearest {brand} store in {city}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("physical_retail",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_certification",
        fact_type="product", fact_key="certifications", severity="critical",
        review_instruction=(
            "An AI answer states a product certification (for example halal or a "
            "product notification) that differs from the approved fact. Check the "
            "certifying body's listing before responding; a shopper may buy on the "
            "strength of that answer."
        ),
    ),
    RiskRule(
        id="wrong_return_policy",
        fact_type="returns", fact_key="policy", severity="high",
        review_instruction=(
            "An AI answer describes a return or refund policy that differs from the "
            "approved fact. Confirm the current policy."
        ),
    ),
    RiskRule(
        id="wrong_warranty",
        fact_type="warranty", fact_key="terms", severity="high",
        review_instruction=(
            "An AI answer describes warranty terms that differ from the approved "
            "fact. Confirm what the warranty covers and for how long."
        ),
    ),
    RiskRule(
        id="invented_product",
        fact_type="product", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes a product or product claim the approved facts do "
            "not support. Confirm what the business sells."
        ),
    ),
    RiskRule(
        id="wrong_price",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes prices that differ from the approved fact. Confirm "
            "the current price range."
        ),
    ),
    RiskRule(
        id="wrong_shipping",
        fact_type="shipping", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer describes shipping coverage, cost or timing that differs "
            "from the approved facts. Confirm the current delivery terms."
        ),
    ),
    RiskRule(
        id="wrong_marketplace",
        fact_type="channel", fact_key="marketplaces", severity="low",
        review_instruction=(
            "An AI answer says the business sells on a marketplace the approved fact "
            "does not list. Confirm where its official stores are."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="official_marketplace_store", label="Official marketplace store"),
    TrustedSourceType(key="certification_body", label="Certifying body's listing"),
    TrustedSourceType(key="company_registry", label="Company registry (e.g. SSM)"),
    TrustedSourceType(key="consumer_review_site", label="Consumer review site"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

# Online-only shops have no premises, so they default to Organization; only a
# physical store gets the LocalBusiness subtype Store.
_SCHEMA = SchemaProfile(
    default_type="Organization",
    subcategory_types=(
        ("physical_retail", "Store"),
    ),
    guidance=(
        "Add `sameAs` only for the business's own official marketplace stores and "
        "social profiles; never invent a store URL.",
        "Do not emit prices, offers or shipping terms; they change often.",
        "Do not emit halal, certification, warranty or return-policy claims. Those "
        "are risk-sensitive facts requiring an approved source.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="shopee_store", name="Shopee official store", asset_type="directory",
        provenance_domain="shopee.com.my", url_hint="https://shopee.com.my/",
    ),
    AuthorityTarget(
        key="lazada_store", name="Lazada official store", asset_type="directory",
        provenance_domain="lazada.com.my", url_hint="https://www.lazada.com.my/",
    ),
    AuthorityTarget(
        key="tiktok_shop", name="TikTok Shop store", asset_type="directory",
        provenance_domain="shop.tiktok.com", url_hint="https://seller-my.tiktok.com/",
    ),
)

_PRIORITY_ASSETS = ("shopee_store", "lazada_store", "instagram", "facebook")

ECOMMERCE_PACK = IndustryPack(
    key="ecommerce",
    version="1.0.0",
    report_fact_label="Product, pricing and after-sales information reviewed",
    label="Retail & E-commerce",
    subcategories=(
        "dtc_brand", "marketplace_seller", "multi_brand_retailer", "physical_retail",
        "other_retail",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(ECOMMERCE_PACK)
