// Single source of truth for the industry picklist used across the onboarding
// wizard, the prospect quick-form, and client settings. Keep this list in sync
// — do not redefine it per component.
export const INDUSTRIES = [
  "Technology",
  "SaaS",
  "E-commerce",
  "Healthcare",
  "Finance",
  "Insurance",
  "Legal & Accounting",
  "Education",
  "Real Estate",
  "Renovation & Interior Design",
  "Food & Beverage",
  "Retail",
  "Hospitality",
  "Automotive",
  "Other",
] as const

// Settings may load a client whose stored industry predates the current list
// (or was set elsewhere). Surface it as the first option so it isn't silently
// dropped from the dropdown.
export function industryOptions(current?: string | null): string[] {
  if (!current || (INDUSTRIES as readonly string[]).includes(current)) {
    return [...INDUSTRIES]
  }
  return [current, ...INDUSTRIES]
}
