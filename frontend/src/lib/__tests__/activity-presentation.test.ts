import { describe, expect, it } from "vitest"
import { presentActivityType } from "../activity-presentation"

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
