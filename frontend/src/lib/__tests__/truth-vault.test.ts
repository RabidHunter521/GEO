import { afterEach, describe, expect, it, vi } from "vitest"
import { deactivateBusinessLocation, getAllTruthFacts } from "../api"
import { primaryReplacementCandidates } from "../truth-vault"
import type { BusinessLocation } from "@/types"

describe("getAllTruthFacts", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("requests every backend page when a scope has more than one hundred facts", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({
        facts: Array.from({ length: 100 }, (_, index) => ({ id: `fact-${index + 1}` })), total: 101,
      }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({
        facts: [{ id: "fact-101" }], total: 101,
      }) })
    vi.stubGlobal("fetch", fetchMock)

    const facts = await getAllTruthFacts("client-1", { location_id: "location-1", mode: "history" })

    expect(facts).toHaveLength(101)
    expect(facts[0].id).toBe("fact-1")
    expect(facts[100].id).toBe("fact-101")
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/v1/clients/client-1/truth-facts?location_id=location-1&mode=history&page=1&page_size=100",
      "http://localhost:8000/api/v1/clients/client-1/truth-facts?location_id=location-1&mode=history&page=2&page_size=100",
    ])
  })
})

describe("primaryReplacementCandidates", () => {
  it("offers only another active location before a primary can be deactivated", () => {
    const locations = [
      { id: "primary", active: true, is_primary: true },
      { id: "replacement", active: true, is_primary: false },
      { id: "inactive", active: false, is_primary: false },
    ] as BusinessLocation[]

    expect(primaryReplacementCandidates(locations, "primary").map((location) => location.id))
      .toEqual(["replacement"])
  })
})

describe("deactivateBusinessLocation", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("sends the chosen replacement with a primary-location deactivation", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 })
    vi.stubGlobal("fetch", fetchMock)

    await deactivateBusinessLocation("client-1", "primary-1", "replacement-1")

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/clients/client-1/locations/primary-1",
      expect.objectContaining({
        method: "DELETE",
        body: JSON.stringify({ replacement_location_id: "replacement-1" }),
      }),
    )
  })
})
