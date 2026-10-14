"""Legal and accounting intelligence pack.

For law firms, accounting and audit firms, company secretaries and bookkeeping
or payroll services. Business-software and SME-financing clients stay in the
B2B & Online Services pack.

A client hires a professional on trust, so the defining risks are claims about
who may do the work: a practising certificate, firm registration or licence the
firm does not hold, or a qualification a named professional does not have. A
wrong fee is corrected at the first meeting; an unqualified adviser is not.

Discovery questions come from the approved practice areas ("Best firm for
divorce in Kuala Lumpur", "How much does a company audit cost in Malaysia?"),
because a buyer searches for the problem, not for a firm.

Professional advertising rules restrict claims about results, so the schema
guidance forbids publishing success rates as well as licences and fees.
Instructions describe what a reviewer should CHECK. None asserts that anyone
is or is not entitled to practise -- SeenBy reports what an AI system said.
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
    # --- what the firm does
    TruthFieldDefinition(
        key="areas",
        label="Practice areas or services (e.g. divorce, conveyancing, audit, tax filing)",
        value_type="list", scope="brand", fact_type="practice", required=True,
    ),
    TruthFieldDefinition(
        key="not_offered", label="Work the firm does not take on", value_type="list",
        scope="brand", fact_type="practice",
    ),
    TruthFieldDefinition(
        key="client_types", label="Who it acts for (e.g. individuals, SMEs, listed companies)",
        value_type="list", scope="brand", fact_type="practice",
    ),

    # --- the people: qualifications are risk-sensitive
    TruthFieldDefinition(
        key="names", label="Partners and key professionals", value_type="list",
        scope="either", fact_type="professional",
    ),
    TruthFieldDefinition(
        key="qualifications",
        label="Professional qualifications (e.g. Advocate & Solicitor, CA(M), ACCA)",
        value_type="text", scope="either", fact_type="professional", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="languages", label="Languages spoken", value_type="list",
        scope="either", fact_type="professional",
    ),

    # --- regulatory: who may do the work
    TruthFieldDefinition(
        key="licences",
        label="Licences and registrations held (e.g. practising certificate, audit "
              "licence, licensed secretary, tax agent)",
        value_type="list", scope="brand", fact_type="regulatory", risk_sensitive=True,
    ),
    TruthFieldDefinition(
        key="regulator", label="Professional body or regulator", value_type="text",
        scope="brand", fact_type="regulatory", risk_sensitive=True,
    ),

    # --- fees and first contact
    TruthFieldDefinition(
        key="model", label="Fee structure (e.g. fixed fee, hourly, retainer)",
        value_type="text", scope="brand", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="price_range", label="Typical fees", value_type="text",
        scope="brand", fact_type="pricing",
    ),
    TruthFieldDefinition(
        key="free_first", label="Free first consultation", value_type="boolean",
        scope="brand", fact_type="consultation",
    ),
    TruthFieldDefinition(
        key="channels", label="Consultation options (in person, video, phone)",
        value_type="list", scope="brand", fact_type="consultation",
    ),

    TruthFieldDefinition(
        key="founded", label="Year founded", value_type="text",
        scope="brand", fact_type="company",
    ),
)

# {practice_area} comes from approved practice facts only. Generic wording
# ("firm", not "lawyer") so the same question reads right for an accountant.
_QUERY_TEMPLATES = (
    # awareness
    QueryTemplate(
        id="brand_overview", template="What is {brand}?",
        buyer_stage="awareness", commercial_intent="low", location_required=False,
    ),
    # consideration
    QueryTemplate(
        id="brand_reputable", template="Is {brand} a reputable {industry}?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
    ),
    QueryTemplate(
        id="practice_cost", template="How much does {practice_area} cost in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
    ),
    QueryTemplate(
        id="country_best", template="Which {industry} is the best in {country}?",
        buyer_stage="consideration", commercial_intent="medium", location_required=True,
    ),
    # decision
    QueryTemplate(
        id="practice_best_city", template="Best firm for {practice_area} in {city}",
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
        id="law_best_lawyer", template="Best lawyer for {practice_area} in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("law_firm",),
    ),
    QueryTemplate(
        id="law_affordable", template="Affordable lawyer in {city}",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("law_firm",),
    ),
    QueryTemplate(
        id="law_brand_consultation", template="Does {brand} offer a free first consultation?",
        buyer_stage="consideration", commercial_intent="medium", location_required=False,
        subcategories=("law_firm",),
    ),
    QueryTemplate(
        id="acct_best_audit", template="Best audit firm for SMEs in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("accounting_firm",),
    ),
    QueryTemplate(
        id="acct_tax_filing",
        template="Which accounting firm handles tax filing for small businesses in {country}?",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("accounting_firm",),
    ),
    QueryTemplate(
        id="cosec_best", template="Best company secretary in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("company_secretary",),
    ),
    QueryTemplate(
        id="cosec_cost", template="How much does a company secretary cost in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("company_secretary",),
    ),
    QueryTemplate(
        id="cosec_brand_licensed", template="Is {brand} a licensed company secretary?",
        buyer_stage="consideration", commercial_intent="high", location_required=False,
        subcategories=("company_secretary",),
    ),
    QueryTemplate(
        id="books_best_sme",
        template="Best bookkeeping service for small businesses in {country}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("bookkeeping",),
    ),
    QueryTemplate(
        id="books_payroll", template="Affordable payroll service in {city}",
        buyer_stage="decision", commercial_intent="high", location_required=True,
        subcategories=("bookkeeping",),
    ),
    QueryTemplate(
        id="books_einvoice",
        template="Which bookkeeping services help with e-invoicing in {country}?",
        buyer_stage="consideration", commercial_intent="high", location_required=True,
        subcategories=("bookkeeping",),
    ),
)

_RISK_RULES = (
    RiskRule(
        id="false_licence_claim",
        fact_type="regulatory", fact_key="licences", severity="critical",
        review_instruction=(
            "An AI answer states a practising certificate, licence or registration "
            "that differs from the approved fact. Check the professional body's "
            "public register before responding; a client may hire the firm on the "
            "strength of that answer."
        ),
    ),
    RiskRule(
        id="wrong_qualification",
        fact_type="professional", fact_key="qualifications", severity="high",
        review_instruction=(
            "An AI answer describes a professional qualification that differs from "
            "the approved fact. Confirm against the professional body's member "
            "listing before responding."
        ),
    ),
    RiskRule(
        id="wrong_regulator",
        fact_type="regulatory", fact_key="regulator", severity="high",
        review_instruction=(
            "An AI answer names a professional body or regulator that differs from "
            "the approved fact. Confirm which body the firm is registered with."
        ),
    ),
    RiskRule(
        id="invented_practice_area",
        fact_type="practice", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer says the firm handles work the approved facts do not list. "
            "Confirm what the firm takes on; a client may contact it for work it "
            "does not do."
        ),
    ),
    RiskRule(
        id="wrong_fees",
        fact_type="pricing", fact_key=None, severity="medium",
        review_instruction=(
            "An AI answer quotes fees that differ from the approved fact. Confirm the "
            "current fee structure."
        ),
    ),
    RiskRule(
        id="wrong_consultation_terms",
        fact_type="consultation", fact_key=None, severity="low",
        review_instruction=(
            "An AI answer describes consultation terms that differ from the approved "
            "facts. Confirm whether a first consultation is free and how it is held."
        ),
    ),
)

_TRUSTED_SOURCES = (
    TrustedSourceType(key="official_website", label="Official website"),
    TrustedSourceType(key="professional_register", label="Professional body's public register"),
    TrustedSourceType(key="company_registry", label="Company registry (e.g. SSM)"),
    TrustedSourceType(key="engagement_letter", label="Published fee schedule or engagement terms"),
    TrustedSourceType(key="reviewed_publication", label="Reviewed publication"),
)

_SCHEMA = SchemaProfile(
    default_type="ProfessionalService",
    subcategory_types=(
        ("law_firm", "LegalService"),
        ("accounting_firm", "AccountingService"),
        ("bookkeeping", "AccountingService"),
    ),
    guidance=(
        "Add `knowsAbout` only for practice areas the description names.",
        "Do not emit fees or fee ranges; they depend on the matter.",
        "Do not emit licence, practising certificate, regulator or qualification "
        "claims. Those are risk-sensitive facts requiring an approved source.",
        "Do not emit success rates, case results or client outcomes; professional "
        "advertising rules restrict them.",
    ),
)

_AUTHORITY_TARGETS = (
    AuthorityTarget(
        key="malaysian_bar", name="Malaysian Bar law firm directory", asset_type="directory",
        provenance_domain="malaysianbar.org.my", url_hint="https://www.malaysianbar.org.my/",
    ),
    AuthorityTarget(
        key="mia_directory", name="MIA member firm directory", asset_type="directory",
        provenance_domain="mia.org.my", url_hint="https://www.mia.org.my/",
    ),
    AuthorityTarget(
        key="asklegal", name="AskLegal coverage", asset_type="media",
        provenance_domain="asklegal.my", url_hint="https://asklegal.my/",
    ),
)

_PRIORITY_ASSETS = ("gbp", "linkedin", "malaysian_bar", "mia_directory")

LEGAL_ACCOUNTING_PACK = IndustryPack(
    key="legal_accounting",
    version="1.0.0",
    report_fact_label="Practice, licence and qualification information reviewed",
    label="Legal & Accounting",
    subcategories=(
        "law_firm", "accounting_firm", "company_secretary", "bookkeeping",
        "other_professional",
    ),
    truth_fields=_TRUTH_FIELDS,
    query_templates=_QUERY_TEMPLATES,
    risk_rules=_RISK_RULES,
    trusted_sources=_TRUSTED_SOURCES,
    schema_profile=_SCHEMA,
    authority_targets=_AUTHORITY_TARGETS,
    priority_asset_keys=_PRIORITY_ASSETS,
)

registry.register(LEGAL_ACCOUNTING_PACK)
