import { describe, expect, it } from "vitest"
import type { ShareOfSourceHistoryPoint } from "@/types"
import { currentBaseline } from "../share-of-source-trend"

const point = (share: number, coverage_changed = false): ShareOfSourceHistoryPoint => ({
  computed_at: "2026-10-01T00:00:00Z",
  client_share_pct: share,
  total_third_party_sources: 10,
  coverage_changed,
})

describe("currentBaseline", () => {
  it("keeps every point when coverage never changed", () => {
    const points = [point(10), point(20), point(30)]
    expect(currentBaseline(points)).toEqual(points)
  })

  it("starts at the latest coverage change, so a jump is never read as progress", () => {
    const points = [point(10), point(12), point(60, true), point(62)]
    expect(currentBaseline(points).map((p) => p.client_share_pct)).toEqual([60, 62])
  })

  it("leaves a single point when the latest scan is the new baseline", () => {
    const points = [point(10), point(60, true)]
    expect(currentBaseline(points)).toHaveLength(1)
  })

  it("handles an empty history", () => {
    expect(currentBaseline([])).toEqual([])
  })
})
