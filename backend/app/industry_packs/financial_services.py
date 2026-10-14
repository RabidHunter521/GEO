"""Insurance and consumer finance intelligence pack.

For businesses selling financial products to individuals: insurers, takaful
operators, insurance agencies and brokers, licensed financial advisers and
consumer lenders. SME-facing finance (payment gateways, business financing)
stays in the B2B & Online Services pack.

Financial products are where a wrong AI answer does the most lasting harm:
someone buys a policy or takes a loan on the strength of it and finds out at
claim time, or when the first repayment is due. The defining risks are a
licence or representative registration the business does not hold, a
Shariah status it does not have, an interest rate it does not charge, and
coverage the policy does not give. They also make finance the sector most
targeted by impersonation, so "Is {brand} licensed?" is asked of every client.

Discovery questions come from the approved product list ("Best medical card
in Malaysia"), because a buyer shops by product, not by provider.

Instructions describe what a reviewer should CHECK. None asserts that a
business is or is not licensed or approved -- SeenBy reports what an AI system
said and is not a regulator.
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
        key="categories",
        label="Products offered (e.g. medical card, car insurance, personal loan)",
        value_type="list", scope="brand", fact_type="product", required=True,
    ),
    TruthFieldDefinition(
        key="coverage", label="Key coverage or product terms", value_type="text",
        scope="brand", fact_type="product", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="eligibility", label="Eligibility (e.g. age, minimum income)", value_type="text",
        scope="brand", fact_type="product",
    ),
    TruthFieldDefinition(
        key="panel_hospitals", label="Panel hospitals or partner network", value_type="list",
        scope="brand", fact_type="product",
    ),

    # --- price
    TruthFieldDefinition(
        key="price_range", label="Premium or fee range", value_type="text",
        scope="brand", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="interest_rate", label="Interest or profit rate", value_type="text",
        scope="brand", fact_type="pricing", risk_sensitive=True,
    ),

    # --- claims
    TruthFieldDefinition(
        key="process", label="How to make a claim", value_type="text",
        scope="brand", fact_type="claims",
    ),
    TruthFieldDefinition(
        key="turnaround", label="Typical claim turnaround", value_type="text",
        scope="brand", fact_type="claims", risk_sensitive=True,
    ),

    # --- regulatory: every one of these is risk-sensitive
    TruthFieldDefinition(
        key="licences", label="Licences and regulatory approvals held",
        value_type="list", scope="brand", fact_type="regulatory", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="regulator", label="Regulator", value_type="text",
        scope="brand", fact_type="regulatory", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="representative_licence",
        label="Agent or representative registration number",
        value_type="text", scope="either", fact_type="registration", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="status", label="Shariah status (e.g. takaful, Islamic financing)",
        value_type="text", scope="brand", fact_type="shariah", risk_sensitive=True,
    ),

    # --- company identity
    TruthFieldDefinition(
        key="parent", label="Parent company or underwriter", value_type="text",
        scope="brand", fact_type="company",
    ),
)

# {product} comes from approved product facts only. {product}-anchored
# questions without the brand land in `recommendation` (ranked).
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    # consideration
    QueryTemplate(
        id="brand_licensed", template="Is {brand} a licensed {industry}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="product_best_coverage",
        template="Which {product} has the best coverage in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="product_cheapest", template="Cheapest {product} in {country}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="country_best", template="Which {industry} is the best in {country}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="product_best", template="Best {product} in {country}",
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
        id="insurer_fastest_claims",
        template="Which insurer pays claims fastest in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("insurer",),
    ),
    QueryTemplate(
        id="insurer_brand_claims", template="How fast does {brand} pay claims?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("insurer",),
    ),
    QueryTemplate(
        id="takaful_best", template="Best takaful plan in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("takaful_operator",),
    ),
    QueryTemplate(
        id="takaful_brand_shariah", template="Are {brand}'s plans Shariah-approved?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("takaful_operator",),
    ),
    QueryTemplate(
        id="agency_compare_quotes",
        template="Where can I compare insurance quotes in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("insurance_agency",),
    ),
    QueryTemplate(
        id="agency_best_agent", template="Best insurance agent in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("insurance_agency",),
    ),
    QueryTemplate(
        id="adviser_best_planner", template="Best licensed financial planner in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("financial_adviser",),
    ),
    QueryTemplate(
        id="adviser_cost",
        template="How much does a financial adviser cost in {country}?",
        buyer_stage="awareness", commercial_intent="medium", location_required=True,
        subcategories=("financial_adviser",),
    ),
    QueryTemplate(
        id="lender_quick_loan",
        template="Where can I get a personal loan quickly in {country}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("consumer_lender",),
    ),
    QueryTemplate(
        id="lender_licensed_local", template="Licensed moneylenders in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("consumer_lender",),
    ),
    QueryTemplate(
        id="lender_brand_rate", template="What interest rate does {brand} charge?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("consumer_lender",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_licence_claim",
        fact_type="regulatory", fact_key="licences", severity="critical",
        review_instruction=(
            "An AI answer states a licence or regulatory approval that differs from "
            "the approved fact. Check the regulator's public register of licensees "
            "before responding; someone may buy a policy or take a loan on the "
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
        id="wrong_representative_registration",
        fact_type="registration", fact_key="representative_licence", severity="critical",
        review_instruction=(
            "An AI answer states an agent or representative registration that differs "
            "from the approved fact. Check the relevant registration body's records "
            "before responding."
        ),
    ),
    RiskRule(
        id="wrong_shariah_status",
        fact_type="shariah", fact_key="status", severity="critical",
        review_instruction=(
            "An AI answer describes a Shariah status that differs from the approved "
            "fact. Confirm against the business's Shariah committee or adviser "
            "statement; a customer may choose the product for that reason alone."
        ),
    ),
    RiskRule(
        id="wrong_interest_rate",
        fact_type="pricing", fact_key="interest_rate", severity="high",
        review_instruction=(
            "An AI answer quotes an interest or profit rate that differs from the "
            "approved fact. Confirm the current published rate."
        ),
    ),
    RiskRule(
        id="wrong_coverage",
        fact_type="product", fact_key="coverage", severity="high",
        review_instruction=(
            "An AI answer describes coverage or product terms that differ from the "
            "approved fact. Confirm against the product disclosure sheet; a customer "
            "may only find out at claim time."
        ),
    ),
    RiskRule(
        id="wrong_claim_turnaround",
        fact_type="claims", fact_key="turnaround", severity="medium",
        review_instruction=(
            "An AI answer states a claim turnaround that differs from the approved "
            "fact. Confirm the current typical turnaround."
        ),
    ),
    RiskRule(
        id="wrong_premium",
        fact_type="pricing", fact_key="price_range", severity="medium",
        review_instruction=(
            "An AI answer quotes premiums or fees that differ from the approved fact. "
            "Confirm the current range."
        ),
    ),
    RiskRule(
        id="invented_product",
        fact_type="product", fact_key="categories", severity="medium",
        review_instruction=(
            "An AI answer says the business offers a product the approved facts do "
            "not list. Confirm what it sells."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="regulator_register", label="Regulator's register of licensees"),
    TrustedSourceType(key="product_disclosure", label="Product disclosure sheet"),
    TrustedSourceType(key="shariah_statement", label="Shariah committee or adviser statement"),
    TrustedSourceType(key="comparison_site", label="Insurance or loan comparison site"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

_SCHEMA = SchemaProfile(
    default_type="FinancialService",
    subcategory_types=(
        ("insurer", "InsuranceAgency"),
        ("takaful_operator", "InsuranceAgency"),
        ("insurance_agency", "InsuranceAgency"),
    ),
    guidance=(
        "Add `areaServed` with the countries the description names.",
        "Do not emit premiums, fees, interest rates or profit rates; they change "
        "and an outdated figure on the client's own site misleads buyers.",
        "Do not emit licence, regulator, registration, Shariah or coverage claims. "
        "Those are risk-sensitive facts requiring an approved source.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="ringgitplus", name="RinggitPlus listing", asset_type="directory",
        provenance_domain="ringgitplus.com", url_hint="https://ringgitplus.com/",
    ),
    AuthorityTarget(
        key="imoney", name="iMoney listing", asset_type="directory",
        provenance_domain="imoney.my", url_hint="https://www.imoney.my/",
    ),
    AuthorityTarget(
        key="loanstreet", name="Loanstreet listing", asset_type="directory",
        provenance_domain="loanstreet.com.my", url_hint="https://loanstreet.com.my/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "ringgitplus", "imoney", "facebook")

FINANCIAL_SERVICES_PACK = IndustryPack(
    key="financial_services",
    version="1.0.0",
    report_fact_label="Product, licence and Shariah information reviewed",
    label="Insurance & Consumer Finance",
    subcategories=(
        "insurer", "takaful_operator", "insurance_agency", "financial_adviser",
        "consumer_lender", "other_finance",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(FINANCIAL_SERVICES_PACK)
