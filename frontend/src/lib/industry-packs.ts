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

export type PackKey = "healthcare" | "fnb" | "local_services" | "education"

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

export const INDUSTRY_PACKS: readonly PackDefinition[] = [HEALTHCARE, FNB, LOCAL_SERVICES, EDUCATION]

export const PACK_KEYS: readonly PackKey[] = INDUSTRY_PACKS.map((pack) => pack.key)

export function packFor(key: string | null | undefined): PackDefinition | null {
  if (!key) return null
  return INDUSTRY_PACKS.find((pack) => pack.key === key) ?? null
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
