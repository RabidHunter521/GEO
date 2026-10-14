/**
 * Frontend mirror of the backend industry pack registry.
 *
 * This file is DUPLICATION and is treated as such: a backend test
 * (test_industry_pack_frontend_mirror.py) fails if a pack key, subcategory or
 * truth-field key exists in app/industry_packs/ but not here. Editing a pack in
 * Python and forgetting this file is caught in CI, not by a client noticing a
 * missing form field.
 *
 * Only what the ADMIN UI needs lives here — labels, input types and which facts
 * demand a source. Query templates and risk rules are deliberately absent: they
 * never render, and copying them would double the drift surface for nothing.
 */

export type PackKey =
  | "healthcare" | "fnb" | "local_services" | "education" | "b2b_services"
  | "property" | "ecommerce" | "hospitality" | "automotive" | "financial_services"
  | "legal_accounting" | "renovation"

/** Mirrors TruthFieldDefinition.value_type in app/industry_packs/base.py. */
export type FactValueType = "text" | "boolean" | "number" | "url" | "list" | "hours"

/** Mirrors TruthFieldDefinition.scope. */
export type FactScope = "brand" | "location" | "either"

export interface PackFactField {
  factType: string
  key: string
  label: string
  valueType: FactValueType
  scope: FactScope
  /** Requires a source URL and reviewer approval before any surface repeats it. */
  riskSensitive?: boolean
  required?: boolean
}

export interface PackDefinition {
  key: PackKey
  label: string
  subcategories: readonly string[]
  fields: readonly PackFactField[]
}

const HEALTHCARE: PackDefinition = {
  key: "healthcare",
  label: "Healthcare",
  subcategories: [
    "general_clinic", "dental", "specialist", "aesthetic",
    "physiotherapy", "diagnostics", "pharmacy", "other_healthcare",
  ],
  fields: [
    { factType: "practitioner", key: "name", label: "Practitioner name", valueType: "text", scope: "location", required: true },
    { factType: "practitioner", key: "qualification", label: "Qualification", valueType: "text", scope: "location", riskSensitive: true },
    { factType: "practitioner", key: "registration_number", label: "Professional registration number", valueType: "text", scope: "location", riskSensitive: true },
    { factType: "practitioner", key: "specialty", label: "Practitioner specialty", valueType: "text", scope: "location", riskSensitive: true },
    { factType: "practitioner", key: "languages", label: "Languages spoken", valueType: "list", scope: "location" },
    { factType: "specialty", key: "offered", label: "Specialties offered", valueType: "list", scope: "either", riskSensitive: true, required: true },
    { factType: "treatment", key: "offered", label: "Treatments offered", valueType: "list", scope: "either", riskSensitive: true, required: true },
    { factType: "treatment", key: "not_offered", label: "Treatments explicitly not offered", valueType: "list", scope: "either" },
    { factType: "treatment", key: "price_range", label: "Treatment price range", valueType: "text", scope: "either" },
    { factType: "accreditation", key: "body", label: "Accrediting body", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "accreditation", key: "valid_until", label: "Accreditation valid until", valueType: "text", scope: "either" },
    { factType: "facility", key: "name", label: "Facility name", valueType: "text", scope: "location", required: true },
    { factType: "facility", key: "services", label: "On-site services", valueType: "list", scope: "location" },
    { factType: "facility", key: "accessibility", label: "Accessibility provisions", valueType: "list", scope: "location" },
    { factType: "payment", key: "methods", label: "Payment methods accepted", valueType: "list", scope: "either" },
    { factType: "payment", key: "insurance_panels", label: "Insurance panels accepted", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "payment", key: "instalment_available", label: "Instalment plans available", valueType: "boolean", scope: "either" },
  ],
}

const FNB: PackDefinition = {
  key: "fnb",
  label: "Food & Beverage",
  subcategories: [
    "restaurant", "cafe", "bakery", "bar", "catering",
    "food_delivery", "quick_service", "other_fnb",
  ],
  fields: [
    { factType: "outlet", key: "name", label: "Outlet name", valueType: "text", scope: "location", required: true },
    { factType: "outlet", key: "seating_capacity", label: "Seating capacity", valueType: "number", scope: "location" },
    { factType: "outlet", key: "dine_in_available", label: "Dine-in available", valueType: "boolean", scope: "location" },
    { factType: "hours", key: "operating", label: "Operating hours", valueType: "hours", scope: "location", required: true },
    { factType: "hours", key: "kitchen", label: "Kitchen hours", valueType: "hours", scope: "location" },
    { factType: "hours", key: "last_order", label: "Last order time", valueType: "text", scope: "location" },
    { factType: "menu", key: "signature_dishes", label: "Signature dishes", valueType: "list", scope: "either", required: true },
    { factType: "menu", key: "items", label: "Menu items", valueType: "list", scope: "either" },
    { factType: "menu", key: "menu_url", label: "Menu URL", valueType: "url", scope: "either" },
    { factType: "cuisine", key: "types", label: "Cuisine types", valueType: "list", scope: "either", required: true },
    { factType: "dietary", key: "halal_status", label: "Halal status", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "dietary", key: "halal_certifier", label: "Halal certifying body", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "dietary", key: "options", label: "Dietary options offered", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "dietary", key: "allergens", label: "Allergen information", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "pricing", key: "price_range", label: "Price range", valueType: "text", scope: "either" },
    { factType: "pricing", key: "set_menu_price", label: "Set menu price", valueType: "text", scope: "either" },
    { factType: "reservation", key: "accepted", label: "Reservations accepted", valueType: "boolean", scope: "either" },
    { factType: "reservation", key: "booking_url", label: "Booking URL", valueType: "url", scope: "either" },
    { factType: "delivery", key: "available", label: "Delivery available", valueType: "boolean", scope: "either" },
    { factType: "delivery", key: "platforms", label: "Delivery platforms", valueType: "list", scope: "either" },
    { factType: "facility", key: "amenities", label: "Facilities", valueType: "list", scope: "location" },
    { factType: "occasion", key: "suitable_for", label: "Occasions catered for", valueType: "list", scope: "either" },
  ],
}

const LOCAL_SERVICES: PackDefinition = {
  key: "local_services",
  label: "Local Services",
  subcategories: [
    "home_maintenance", "automotive", "beauty_wellness", "cleaning",
    "repair", "professional_local", "emergency_service", "other_local_service",
  ],
  fields: [
    { factType: "service", key: "catalog", label: "Services offered", valueType: "list", scope: "either", required: true },
    { factType: "service", key: "exclusions", label: "Services explicitly not offered", valueType: "list", scope: "either" },
    { factType: "service", key: "specialisations", label: "Specialisations", valueType: "list", scope: "either" },
    { factType: "coverage", key: "areas", label: "Service areas covered", valueType: "list", scope: "either", riskSensitive: true, required: true },
    { factType: "coverage", key: "travel_radius_km", label: "Travel radius (km)", valueType: "number", scope: "either" },
    { factType: "coverage", key: "callout_fee_applies", label: "Callout fee outside base area", valueType: "boolean", scope: "either" },
    { factType: "availability", key: "emergency", label: "Emergency callout available", valueType: "boolean", scope: "either", riskSensitive: true },
    { factType: "availability", key: "same_day", label: "Same-day service available", valueType: "boolean", scope: "either", riskSensitive: true },
    { factType: "availability", key: "response_time", label: "Typical response time", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "availability", key: "operating_hours", label: "Operating hours", valueType: "hours", scope: "location" },
    { factType: "licensing", key: "held", label: "Licences and certifications held", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "licensing", key: "reference_number", label: "Licence reference number", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "insurance", key: "public_liability", label: "Public liability cover", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "insurance", key: "workmanship_cover", label: "Workmanship cover", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "pricing", key: "model", label: "Pricing model", valueType: "text", scope: "either", required: true },
    { factType: "pricing", key: "callout_fee", label: "Callout fee", valueType: "text", scope: "either" },
    { factType: "pricing", key: "free_quote", label: "Free quotation offered", valueType: "boolean", scope: "either" },
    { factType: "warranty", key: "terms", label: "Warranty or guarantee terms", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "warranty", key: "duration", label: "Warranty duration", valueType: "text", scope: "either" },
    { factType: "booking", key: "channel", label: "How to book", valueType: "text", scope: "either" },
    { factType: "booking", key: "booking_url", label: "Booking URL", valueType: "url", scope: "either" },
  ],
}

const EDUCATION: PackDefinition = {
  key: "education",
  label: "Education",
  subcategories: [
    "tuition_centre", "enrichment", "kindergarten",
    "international_school", "private_school",
    "language_centre", "driving_school", "other_education",
  ],
  fields: [
    { factType: "teacher", key: "name", label: "Teacher or principal name", valueType: "text", scope: "location", required: true },
    { factType: "teacher", key: "qualification", label: "Teaching qualification", valueType: "text", scope: "location", riskSensitive: true },
    { factType: "teacher", key: "subjects", label: "Subjects taught", valueType: "list", scope: "location" },
    { factType: "teacher", key: "languages", label: "Languages of instruction", valueType: "list", scope: "location" },
    { factType: "programme", key: "offered", label: "Subjects or programmes offered", valueType: "list", scope: "either", riskSensitive: true, required: true },
    { factType: "programme", key: "curriculum", label: "Curriculum followed", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "programme", key: "levels", label: "Levels or year groups taught", valueType: "list", scope: "either" },
    { factType: "programme", key: "class_size", label: "Typical class size", valueType: "number", scope: "either" },
    { factType: "programme", key: "not_offered", label: "Subjects explicitly not offered", valueType: "list", scope: "either" },
    { factType: "accreditation", key: "body", label: "Registering or accrediting body", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "accreditation", key: "registration_number", label: "Registration reference number", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "accreditation", key: "valid_until", label: "Registration valid until", valueType: "text", scope: "either" },
    { factType: "outcomes", key: "results_published", label: "Results the school publishes", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "outcomes", key: "placements", label: "Published onward placements", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "fees", key: "range", label: "Fee range", valueType: "text", scope: "either" },
    { factType: "fees", key: "registration_fee", label: "Registration fee", valueType: "text", scope: "either" },
    { factType: "fees", key: "payment_plans", label: "Instalment plans available", valueType: "boolean", scope: "either" },
    { factType: "campus", key: "name", label: "Campus name", valueType: "text", scope: "location", required: true },
    { factType: "campus", key: "amenities", label: "Campus amenities", valueType: "list", scope: "location" },
    { factType: "campus", key: "transport_provided", label: "School transport provided", valueType: "boolean", scope: "location" },
    { factType: "admissions", key: "intake_months", label: "Intake months", valueType: "list", scope: "either" },
    { factType: "admissions", key: "age_range", label: "Age range accepted", valueType: "text", scope: "either" },
    { factType: "admissions", key: "entrance_assessment", label: "Entrance assessment required", valueType: "boolean", scope: "either" },
  ],
}

const B2B_SERVICES: PackDefinition = {
  key: "b2b_services",
  label: "B2B & Online Services",
  subcategories: [
    "payment_gateway", "business_software", "sme_financing", "professional_services", "logistics", "other_b2b",
  ],
  fields: [
    { factType: "service", key: "catalog", label: "Products or services offered", valueType: "list", scope: "brand", required: true },
    { factType: "service", key: "specialisations", label: "Specialisations", valueType: "list", scope: "brand" },
    { factType: "service", key: "exclusions", label: "Products or services explicitly not offered", valueType: "list", scope: "brand" },
    { factType: "market", key: "countries", label: "Countries served", valueType: "list", scope: "brand", required: true },
    { factType: "market", key: "customer_segments", label: "Customer segments served", valueType: "list", scope: "brand" },
    { factType: "pricing", key: "model", label: "Pricing model", valueType: "text", scope: "brand", required: true },
    { factType: "pricing", key: "published_rates", label: "Published fees or rates", valueType: "text", scope: "brand" },
    { factType: "pricing", key: "setup_fee", label: "Setup fee", valueType: "text", scope: "brand" },
    { factType: "integration", key: "platforms", label: "Platforms it integrates with", valueType: "list", scope: "brand" },
    { factType: "integration", key: "api_available", label: "Public API available", valueType: "boolean", scope: "brand" },
    { factType: "payment", key: "methods_supported", label: "Payment methods supported", valueType: "list", scope: "brand", riskSensitive: true },
    { factType: "payment", key: "settlement_time", label: "Typical settlement time", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "regulatory", key: "licences", label: "Licences and regulatory approvals held", valueType: "list", scope: "brand", riskSensitive: true },
    { factType: "regulatory", key: "regulator", label: "Regulator", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "security", key: "certifications", label: "Security certifications (e.g. PCI DSS)", valueType: "list", scope: "brand", riskSensitive: true },
    { factType: "support", key: "channels", label: "Support channels", valueType: "list", scope: "brand" },
    { factType: "support", key: "hours", label: "Support hours", valueType: "text", scope: "brand" },
    { factType: "onboarding", key: "time", label: "Typical onboarding time", valueType: "text", scope: "brand" },
    { factType: "company", key: "parent", label: "Parent company", valueType: "text", scope: "brand" },
    { factType: "company", key: "founded", label: "Year founded", valueType: "text", scope: "brand" },
  ],
}

const PROPERTY: PackDefinition = {
  key: "property",
  label: "Property & Real Estate",
  subcategories: [
    "developer", "real_estate_agency", "property_management", "co_living", "other_property",
  ],
  fields: [
    { factType: "project", key: "names", label: "Projects, developments or buildings", valueType: "list", scope: "either", required: true },
    { factType: "project", key: "areas", label: "Areas with projects or listings", valueType: "list", scope: "either", required: true },
    { factType: "project", key: "types", label: "Property types (e.g. condominium, landed, shop lot)", valueType: "list", scope: "either" },
    { factType: "project", key: "tenure", label: "Tenure (freehold or leasehold)", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "project", key: "completion", label: "Completion or handover status", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "project", key: "track_record", label: "Completed projects or track record", valueType: "text", scope: "brand" },
    { factType: "service", key: "catalog", label: "Services offered", valueType: "list", scope: "brand" },
    { factType: "pricing", key: "price_range", label: "Price range", valueType: "text", scope: "either", required: true },
    { factType: "pricing", key: "rental_range", label: "Rental range", valueType: "text", scope: "either" },
    { factType: "incentive", key: "offers", label: "Current buyer incentives (e.g. rebates, free legal fees)", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "financing", key: "partner_banks", label: "Partner banks for financing", valueType: "list", scope: "either" },
    { factType: "registration", key: "developer_licence", label: "Housing developer licence number", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "registration", key: "agency_registration", label: "Estate agency registration number", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "facility", key: "amenities", label: "Facilities", valueType: "list", scope: "location" },
  ],
}

const ECOMMERCE: PackDefinition = {
  key: "ecommerce",
  label: "Retail & E-commerce",
  subcategories: [
    "dtc_brand", "marketplace_seller", "multi_brand_retailer", "physical_retail", "other_retail",
  ],
  fields: [
    { factType: "product", key: "categories", label: "Product categories sold", valueType: "list", scope: "brand", required: true },
    { factType: "product", key: "hero_products", label: "Best-selling or hero products", valueType: "list", scope: "brand" },
    { factType: "product", key: "certifications", label: "Product certifications (e.g. halal, product notification, SIRIM)", valueType: "list", scope: "brand", riskSensitive: true },
    { factType: "product", key: "origin", label: "Where the brand is from or made", valueType: "text", scope: "brand" },
    { factType: "channel", key: "marketplaces", label: "Marketplaces sold on (e.g. Shopee, Lazada, TikTok Shop)", valueType: "list", scope: "brand" },
    { factType: "channel", key: "outlets", label: "Physical stores", valueType: "list", scope: "location" },
    { factType: "pricing", key: "price_range", label: "Price range", valueType: "text", scope: "brand", required: true },
    { factType: "checkout", key: "payment_methods", label: "Payment methods accepted", valueType: "list", scope: "brand" },
    { factType: "shipping", key: "areas", label: "Shipping coverage", valueType: "list", scope: "brand" },
    { factType: "shipping", key: "free_threshold", label: "Free shipping threshold", valueType: "text", scope: "brand" },
    { factType: "shipping", key: "delivery_time", label: "Typical delivery time", valueType: "text", scope: "brand" },
    { factType: "returns", key: "policy", label: "Return and refund policy", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "warranty", key: "terms", label: "Warranty terms", valueType: "text", scope: "brand", riskSensitive: true },
  ],
}

const HOSPITALITY: PackDefinition = {
  key: "hospitality",
  label: "Hospitality & Travel",
  subcategories: [
    "hotel", "resort", "homestay", "tour_operator", "event_venue", "other_hospitality",
  ],
  fields: [
    { factType: "stay", key: "room_types", label: "Room or unit types", valueType: "list", scope: "either" },
    { factType: "stay", key: "facilities", label: "Facilities (e.g. pool, parking, kids' club)", valueType: "list", scope: "location" },
    { factType: "stay", key: "breakfast_included", label: "Breakfast included", valueType: "boolean", scope: "either" },
    { factType: "stay", key: "check_in_out", label: "Check-in and check-out times", valueType: "text", scope: "location" },
    { factType: "occasion", key: "suitable_for", label: "Occasions catered for (e.g. family trips, weddings)", valueType: "list", scope: "either", required: true },
    { factType: "nearby", key: "attractions", label: "Nearby attractions or landmarks", valueType: "list", scope: "location" },
    { factType: "tour", key: "destinations", label: "Tour destinations", valueType: "list", scope: "brand" },
    { factType: "tour", key: "itineraries", label: "Tour packages or itineraries", valueType: "list", scope: "brand" },
    { factType: "venue", key: "capacity", label: "Event capacity (guests)", valueType: "number", scope: "location" },
    { factType: "pricing", key: "price_range", label: "Price or rate range", valueType: "text", scope: "either", required: true },
    { factType: "policy", key: "cancellation", label: "Cancellation policy", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "policy", key: "children", label: "Child and extra-bed policy", valueType: "text", scope: "either" },
    { factType: "dietary", key: "halal_status", label: "Halal or Muslim-friendly status", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "registration", key: "tourism_licence", label: "Tourism licence number", valueType: "text", scope: "brand", riskSensitive: true },
  ],
}

const AUTOMOTIVE: PackDefinition = {
  key: "automotive",
  label: "Automotive Sales",
  subcategories: [
    "new_car_dealer", "used_car_dealer", "ev_dealer", "motorcycle_dealer", "car_rental", "other_automotive",
  ],
  fields: [
    { factType: "vehicle", key: "makes", label: "Makes sold (e.g. Honda, Proton, BYD)", valueType: "list", scope: "either", required: true },
    { factType: "vehicle", key: "models", label: "Models sold", valueType: "list", scope: "either" },
    { factType: "vehicle", key: "types", label: "Vehicle types (e.g. SUV, MPV, EV, motorcycle)", valueType: "list", scope: "either" },
    { factType: "service", key: "catalog", label: "Services offered (e.g. servicing, insurance renewal)", valueType: "list", scope: "either" },
    { factType: "pricing", key: "price_range", label: "Price range", valueType: "text", scope: "either", required: true },
    { factType: "finance", key: "loan_partners", label: "Loan partner banks", valueType: "list", scope: "either" },
    { factType: "finance", key: "trade_in", label: "Trade-in accepted", valueType: "boolean", scope: "either" },
    { factType: "dealer", key: "authorised_for", label: "Makes it is an authorised dealer for", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "warranty", key: "terms", label: "Warranty terms", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "inspection", key: "programme", label: "Used-car inspection or certification programme", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "licensing", key: "held", label: "Licences held", valueType: "list", scope: "either", riskSensitive: true },
  ],
}

const FINANCIAL_SERVICES: PackDefinition = {
  key: "financial_services",
  label: "Insurance & Consumer Finance",
  subcategories: [
    "insurer", "takaful_operator", "insurance_agency", "financial_adviser", "consumer_lender", "other_finance",
  ],
  fields: [
    { factType: "product", key: "categories", label: "Products offered (e.g. medical card, car insurance, personal loan)", valueType: "list", scope: "brand", required: true },
    { factType: "product", key: "coverage", label: "Key coverage or product terms", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "product", key: "eligibility", label: "Eligibility (e.g. age, minimum income)", valueType: "text", scope: "brand" },
    { factType: "product", key: "panel_hospitals", label: "Panel hospitals or partner network", valueType: "list", scope: "brand" },
    { factType: "pricing", key: "price_range", label: "Premium or fee range", valueType: "text", scope: "brand" },
    { factType: "pricing", key: "interest_rate", label: "Interest or profit rate", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "claims", key: "process", label: "How to make a claim", valueType: "text", scope: "brand" },
    { factType: "claims", key: "turnaround", label: "Typical claim turnaround", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "regulatory", key: "licences", label: "Licences and regulatory approvals held", valueType: "list", scope: "brand", riskSensitive: true },
    { factType: "regulatory", key: "regulator", label: "Regulator", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "registration", key: "representative_licence", label: "Agent or representative registration number", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "shariah", key: "status", label: "Shariah status (e.g. takaful, Islamic financing)", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "company", key: "parent", label: "Parent company or underwriter", valueType: "text", scope: "brand" },
  ],
}

const LEGAL_ACCOUNTING: PackDefinition = {
  key: "legal_accounting",
  label: "Legal & Accounting",
  subcategories: [
    "law_firm", "accounting_firm", "company_secretary", "bookkeeping", "other_professional",
  ],
  fields: [
    { factType: "practice", key: "areas", label: "Practice areas or services (e.g. divorce, conveyancing, audit, tax filing)", valueType: "list", scope: "brand", required: true },
    { factType: "practice", key: "not_offered", label: "Work the firm does not take on", valueType: "list", scope: "brand" },
    { factType: "practice", key: "client_types", label: "Who it acts for (e.g. individuals, SMEs, listed companies)", valueType: "list", scope: "brand" },
    { factType: "professional", key: "names", label: "Partners and key professionals", valueType: "list", scope: "either" },
    { factType: "professional", key: "qualifications", label: "Professional qualifications (e.g. Advocate & Solicitor, CA(M), ACCA)", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "professional", key: "languages", label: "Languages spoken", valueType: "list", scope: "either" },
    { factType: "regulatory", key: "licences", label: "Licences and registrations held (e.g. practising certificate, audit licence, licensed secretary, tax agent)", valueType: "list", scope: "brand", riskSensitive: true },
    { factType: "regulatory", key: "regulator", label: "Professional body or regulator", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "pricing", key: "model", label: "Fee structure (e.g. fixed fee, hourly, retainer)", valueType: "text", scope: "brand" },
    { factType: "pricing", key: "price_range", label: "Typical fees", valueType: "text", scope: "brand" },
    { factType: "consultation", key: "free_first", label: "Free first consultation", valueType: "boolean", scope: "brand" },
    { factType: "consultation", key: "channels", label: "Consultation options (in person, video, phone)", valueType: "list", scope: "brand" },
    { factType: "company", key: "founded", label: "Year founded", valueType: "text", scope: "brand" },
  ],
}

const RENOVATION: PackDefinition = {
  key: "renovation",
  label: "Renovation & Interior Design",
  subcategories: [
    "general_contractor", "interior_designer", "design_and_build", "carpentry", "landscape", "other_renovation",
  ],
  fields: [
    { factType: "work", key: "types", label: "Types of work (e.g. kitchen renovation, bathroom, extension, wardrobes)", valueType: "list", scope: "either", required: true },
    { factType: "work", key: "property_types", label: "Property types (e.g. condo, landed house, shop lot)", valueType: "list", scope: "either" },
    { factType: "work", key: "not_offered", label: "Work not taken on", valueType: "list", scope: "either" },
    { factType: "design", key: "styles", label: "Design styles (e.g. modern minimalist, Japandi)", valueType: "list", scope: "either" },
    { factType: "project", key: "track_record", label: "Completed projects or portfolio", valueType: "text", scope: "either" },
    { factType: "coverage", key: "areas", label: "Areas served", valueType: "list", scope: "either", required: true, riskSensitive: true },
    { factType: "registration", key: "contractor_registration", label: "Contractor registration (e.g. CIDB grade and number)", valueType: "text", scope: "brand", riskSensitive: true },
    { factType: "licensing", key: "held", label: "Licences and certifications held", valueType: "list", scope: "either", riskSensitive: true },
    { factType: "insurance", key: "public_liability", label: "Public liability cover", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "insurance", key: "workmanship_cover", label: "Workmanship cover", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "warranty", key: "terms", label: "Workmanship warranty or defect liability terms", valueType: "text", scope: "either", riskSensitive: true },
    { factType: "warranty", key: "duration", label: "Warranty duration", valueType: "text", scope: "either" },
    { factType: "pricing", key: "price_range", label: "Typical project price range", valueType: "text", scope: "either", required: true },
    { factType: "pricing", key: "model", label: "Pricing model (e.g. per sq ft, lump sum, design fee)", valueType: "text", scope: "either" },
    { factType: "pricing", key: "free_quote", label: "Free quotation or site visit", valueType: "boolean", scope: "either" },
    { factType: "payment", key: "schedule", label: "Deposit and progress payment terms", valueType: "text", scope: "either", riskSensitive: true },
  ],
}

export const INDUSTRY_PACKS: readonly PackDefinition[] = [
  HEALTHCARE, FNB, LOCAL_SERVICES, EDUCATION, B2B_SERVICES, PROPERTY, ECOMMERCE,
  HOSPITALITY, AUTOMOTIVE, FINANCIAL_SERVICES, LEGAL_ACCOUNTING, RENOVATION,
]

export const PACK_KEYS: readonly PackKey[] = INDUSTRY_PACKS.map((pack) => pack.key)

export function packFor(key: string | null | undefined): PackDefinition | null {
  if (!key) return null
  return INDUSTRY_PACKS.find((pack) => pack.key === key) ?? null
}

/**
 * The pack to SUGGEST for a client's picklist industry (src/lib/industries.ts).
 * A suggestion only: an admin still chooses and saves the pack. Industries no
 * pack fits yet map to null rather than to a near-miss, because a wrong pack
 * asks worse questions than the standard set.
 */
export const SUGGESTED_PACK_BY_INDUSTRY: Record<string, PackKey | null> = {
  Healthcare: "healthcare",
  "Food & Beverage": "fnb",
  Education: "education",
  Technology: "b2b_services",
  SaaS: "b2b_services",
  // Most "Finance" clients sell to consumers (insurers, advisers, lenders).
  // SME-facing finance (payment gateways, business loans) is B2B instead.
  Finance: "financial_services",
  Insurance: "financial_services",
  "Legal & Accounting": "legal_accounting",
  "Renovation & Interior Design": "renovation",
  "E-commerce": "ecommerce",
  "Real Estate": "property",
  Retail: "ecommerce",
  Hospitality: "hospitality",
  Automotive: "automotive",
  Other: null,
}

export function suggestedPackFor(industry: string | null | undefined): PackDefinition | null {
  const key = industry ? SUGGESTED_PACK_BY_INDUSTRY[industry] : null
  return key ? packFor(key) : null
}

/** A pack choice being made while a client is created, before it exists. */
export interface PackChoice {
  pack: PackKey | null
  subcategory: string | null
  buyerTerm: string
  /** True once the admin picked a pack themselves; a suggestion never overrides it. */
  packTouched: boolean
}

export const EMPTY_PACK_CHOICE: PackChoice = {
  pack: null, subcategory: null, buyerTerm: "", packTouched: false,
}

/** The choice after the industry changes: the suggestion, unless the admin already chose. */
export function applyIndustryToChoice(choice: PackChoice, industry: string): PackChoice {
  if (choice.packTouched) return choice
  return { ...choice, pack: suggestedPackFor(industry)?.key ?? null, subcategory: null }
}

/** The fields to PATCH onto a newly created client; empty when nothing was chosen. */
export function packChoiceUpdate(choice: PackChoice): {
  industry_pack?: string
  industry_subcategory?: string
  buyer_term?: string
} {
  const buyerTerm = choice.buyerTerm.trim()
  return {
    ...(choice.pack ? { industry_pack: choice.pack } : {}),
    ...(choice.pack && choice.subcategory ? { industry_subcategory: choice.subcategory } : {}),
    ...(buyerTerm ? { buyer_term: buyerTerm } : {}),
  }
}

export function packLabel(key: string | null | undefined): string {
  return packFor(key)?.label ?? "No pack selected"
}

export function subcategoriesFor(key: string | null | undefined): readonly string[] {
  return packFor(key)?.subcategories ?? []
}

/** Human label for a stored subcategory value ("general_clinic" -> "General clinic"). */
export function subcategoryLabel(value: string): string {
  const spaced = value.replaceAll("_", " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

/** Fact types this pack cares about, in declaration order. */
export function factTypesFor(key: string | null | undefined): string[] {
  const pack = packFor(key)
  if (!pack) return []
  return [...new Set(pack.fields.map((field) => field.factType))]
}

/** Declared fields for one fact type, used to drive the Truth Vault form. */
export function fieldsForFactType(
  key: string | null | undefined,
  factType: string,
): PackFactField[] {
  return packFor(key)?.fields.filter((field) => field.factType === factType) ?? []
}

export function fieldFor(
  key: string | null | undefined,
  factType: string,
  factKey: string,
): PackFactField | null {
  return fieldsForFactType(key, factType).find((field) => field.key === factKey) ?? null
}

export interface PackChangeImpact {
  from: string
  to: string
  /** Pack-specific fields that stop being collected. */
  retiredFields: PackFactField[]
  /** Fields both packs declare, so the stored facts stay meaningful. */
  sharedFields: PackFactField[]
  /** Fields the new pack introduces. */
  newFields: PackFactField[]
  subcategoryCleared: boolean
  benchmarkReset: boolean
}

/**
 * What actually changes if this client switches packs.
 *
 * Approved facts are never deleted by a pack change — a fact the new pack does
 * not declare simply stops being asked about, and its history is preserved.
 * Saying so explicitly is the point: an admin should not have to guess whether
 * switching destroys their reviewed work.
 */
export function impactOfPackChange(
  fromKey: string | null | undefined,
  toKey: string | null | undefined,
): PackChangeImpact {
  const from = packFor(fromKey)
  const to = packFor(toKey)
  const identity = (field: PackFactField) => `${field.factType}.${field.key}`
  const toKeys = new Set((to?.fields ?? []).map(identity))
  const fromKeys = new Set((from?.fields ?? []).map(identity))

  return {
    from: from?.label ?? "No pack",
    to: to?.label ?? "No pack",
    retiredFields: (from?.fields ?? []).filter((f) => !toKeys.has(identity(f))),
    sharedFields: (from?.fields ?? []).filter((f) => toKeys.has(identity(f))),
    newFields: (to?.fields ?? []).filter((f) => !fromKeys.has(identity(f))),
    // The backend clears it on any real pack change; a subcategory is
    // meaningless under a different pack.
    subcategoryCleared: true,
    // Query coverage changes, so prior scans are not comparable like for like.
    benchmarkReset: true,
  }
}
