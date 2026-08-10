import { describe, expect, it } from "vitest"
import { parseUtc, presentActivityType } from "../activity-presentation"

describe("presentActivityType", () => {
  it.each([
    ["authority_assets_added", "Authority opportunities added"],
    ["brief_generated", "Content brief prepared"],
    ["traffic_updated", "AI traffic data updated"],
    ["toolkit_verified", "Technical files checked"],
  ])("maps %s to client-safe copy", (eventType, expected) => {
    const result = presentActivityType(eventType)
    expect(result.label).toBe(expected)
    expect(result.label).not.toContain("_")
  })

  it("humanizes unknown keys instead of exposing raw enums", () => {
    const result = presentActivityType("future_event_key")
    expect(result.label).toBe("Future event key")
    expect(result.label).not.toContain("_")
  })
})

describe("parseUtc", () => {
  it("parses a naive timestamp (no zone suffix) as UTC, not local time", () => {
    const naive = "2026-08-09T10:30:00"
    const explicitUtc = "2026-08-09T10:30:00Z"
    expect(parseUtc(naive).getTime()).toBe(new Date(explicitUtc).getTime())
  })

  it("leaves an already-zoned timestamp untouched", () => {
    const zoned = "2026-08-09T10:30:00+08:00"
    expect(parseUtc(zoned).getTime()).toBe(new Date(zoned).getTime())
  })
})
