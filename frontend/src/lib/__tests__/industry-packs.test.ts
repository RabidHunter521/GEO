import { describe, expect, it } from "vitest"

import {
  INDUSTRY_PACKS,
  PACK_KEYS,
  fieldFor,
  fieldsForFactType,
  factTypesFor,
  impactOfPackChange,
  packFor,
  packLabel,
  subcategoriesFor,
  subcategoryLabel,
} from "../industry-packs"

const VALUE_TYPES = ["text", "boolean", "number", "url", "list", "hours"]
const SCOPES = ["brand", "location", "either"]

describe("catalog shape", () => {
  it("has exactly the three supported packs", () => {
    expect(PACK_KEYS).toEqual(["healthcare", "fnb", "local_services"])
  })

  it("gives every pack a non-empty, unique set of subcategories", () => {
    for (const pack of INDUSTRY_PACKS) {
      expect(pack.subcategories.length).toBeGreaterThan(0)
      expect(new Set(pack.subcategories).size).toBe(pack.subcategories.length)
    }
  })

  it("keeps fact field keys unique within a pack", () => {
    for (const pack of INDUSTRY_PACKS) {
      const ids = pack.fields.map((f) => `${f.factType}.${f.key}`)
      expect(new Set(ids).size).toBe(ids.length)
    }
  })

  it("uses only input types the form can render", () => {
    for (const pack of INDUSTRY_PACKS) {
      for (const field of pack.fields) {
        expect(VALUE_TYPES).toContain(field.valueType)
        expect(SCOPES).toContain(field.scope)
      }
    }
  })

  it("gives every field a human label", () => {
    for (const pack of INDUSTRY_PACKS) {
      for (const field of pack.fields) {
        expect(field.label.trim().length).toBeGreaterThan(0)
      }
    }
  })
})

describe("lookups", () => {
  it("returns null rather than throwing for an unknown or absent pack", () => {
    expect(packFor("retail")).toBeNull()
    expect(packFor(null)).toBeNull()
    expect(packFor(undefined)).toBeNull()
    expect(subcategoriesFor("retail")).toEqual([])
    expect(factTypesFor(null)).toEqual([])
    expect(fieldsForFactType(null, "practitioner")).toEqual([])
    expect(fieldFor("retail", "practitioner", "qualification")).toBeNull()
  })

  it("labels an unselected pack honestly", () => {
    expect(packLabel(null)).toBe("No pack selected")
    expect(packLabel("healthcare")).toBe("Healthcare")
  })

  it("lists fact types in declaration order without duplicates", () => {
    const types = factTypesFor("healthcare")
    expect(types[0]).toBe("practitioner")
    expect(new Set(types).size).toBe(types.length)
  })

  it("finds the fields for one fact type only", () => {
    const fields = fieldsForFactType("healthcare", "practitioner")
    expect(fields.length).toBeGreaterThan(0)
    expect(fields.every((f) => f.factType === "practitioner")).toBe(true)
  })

  it("marks credential facts as risk sensitive", () => {
    expect(fieldFor("healthcare", "practitioner", "qualification")?.riskSensitive).toBe(true)
    expect(fieldFor("fnb", "dietary", "halal_status")?.riskSensitive).toBe(true)
    expect(fieldFor("local_services", "licensing", "held")?.riskSensitive).toBe(true)
  })

  it("does not mark ordinary detail facts as risk sensitive", () => {
    expect(fieldFor("fnb", "hours", "operating")?.riskSensitive).toBeUndefined()
    expect(fieldFor("healthcare", "payment", "methods")?.riskSensitive).toBeUndefined()
  })

  it("humanises stored subcategory values", () => {
    expect(subcategoryLabel("general_clinic")).toBe("General clinic")
    expect(subcategoryLabel("other_fnb")).toBe("Other fnb")
  })
})

describe("pack change impact", () => {
  it("separates retired, shared and new fields", () => {
    const impact = impactOfPackChange("healthcare", "fnb")

    expect(impact.from).toBe("Healthcare")
    expect(impact.to).toBe("Food & Beverage")
    expect(impact.retiredFields.length).toBeGreaterThan(0)
    expect(impact.newFields.length).toBeGreaterThan(0)
    // facility.name is declared by healthcare but not F&B, so it retires
    expect(impact.retiredFields.some((f) => f.factType === "practitioner")).toBe(true)
    expect(impact.newFields.some((f) => f.factType === "dietary")).toBe(true)
  })

  it("counts a field declared by both packs as shared, not retired", () => {
    const impact = impactOfPackChange("healthcare", "fnb")
    const identity = (f: { factType: string; key: string }) => `${f.factType}.${f.key}`
    const retired = new Set(impact.retiredFields.map(identity))
    for (const field of impact.sharedFields) {
      expect(retired.has(identity(field))).toBe(false)
    }
  })

  it("always reports the subcategory and benchmark consequences", () => {
    const impact = impactOfPackChange("fnb", "local_services")
    expect(impact.subcategoryCleared).toBe(true)
    expect(impact.benchmarkReset).toBe(true)
  })

  it("describes a first-time selection without inventing a previous pack", () => {
    const impact = impactOfPackChange(null, "healthcare")
    expect(impact.from).toBe("No pack")
    expect(impact.retiredFields).toEqual([])
    expect(impact.newFields.length).toBeGreaterThan(0)
  })
})
