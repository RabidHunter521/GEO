import { describe, expect, it } from "vitest"
import { validNextStatuses } from "../delivery-lifecycle"

describe("validNextStatuses", () => {
  it("mirrors the outcome action lifecycle graph", () => {
    expect(validNextStatuses("recommended")).toEqual([
      "approved_internal",
      "dismissed",
      "superseded",
    ])
    expect(validNextStatuses("ready_to_publish")).toEqual([
      "published",
      "in_progress",
    ])
    expect(validNextStatuses("verified")).toEqual([])
  })
})
