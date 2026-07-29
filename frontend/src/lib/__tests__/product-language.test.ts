import { describe, expect, it } from "vitest"
import {
  PRODUCT_LANGUAGE,
  evidenceLabel,
  type EvidenceLevel,
} from "../product-language"

describe("product language", () => {
  it("separates readiness from AI presence", () => {
    expect(PRODUCT_LANGUAGE.readiness).toBe("Growth Readiness")
    expect(PRODUCT_LANGUAGE.presence).toBe("AI Presence")
    expect(PRODUCT_LANGUAGE.readiness).not.toBe(PRODUCT_LANGUAGE.presence)
  })

  it.each([
    ["observed", "Observed"],
    ["attributed", "Attributed"],
    ["assisted", "Assisted"],
    ["estimated", "Estimated"],
  ] satisfies Array<[EvidenceLevel, string]>)(
    "labels %s evidence",
    (level, expected) => {
      expect(evidenceLabel(level)).toBe(expected)
    },
  )
})
