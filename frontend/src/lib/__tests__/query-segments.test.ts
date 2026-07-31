import { describe, expect, it } from "vitest"
import { segmentQueries, type QuerySegmentFlags } from "../query-segments"

interface Row {
  id: string
  seen: boolean
  newlySeen?: boolean
  newlyLost?: boolean
}

function flagsOf(row: Row): QuerySegmentFlags {
  return { seen: row.seen, newlySeen: row.newlySeen, newlyLost: row.newlyLost }
}

describe("segmentQueries — total partition", () => {
  it("places every item in exactly one segment and drops none", () => {
    const rows: Row[] = [
      { id: "a", seen: true, newlySeen: true },
      { id: "b", seen: false, newlyLost: true },
      { id: "c", seen: false },
      { id: "d", seen: true },
      { id: "e", seen: true, newlySeen: false, newlyLost: false },
      { id: "f", seen: false, newlySeen: false },
    ]

    const segments = segmentQueries(rows, flagsOf)

    const totalOut =
      segments.newlySeen.length +
      segments.newlyLost.length +
      segments.opportunities.length +
      segments.other.length
    expect(totalOut).toBe(rows.length)

    // No id appears twice across segments, and every input id appears exactly once.
    const allIds = [
      ...segments.newlySeen,
      ...segments.newlyLost,
      ...segments.opportunities,
      ...segments.other,
    ].map((r) => r.id)
    expect(new Set(allIds).size).toBe(allIds.length)
    expect(new Set(allIds)).toEqual(new Set(rows.map((r) => r.id)))
  })

  it("returns four empty arrays for an empty input, never throwing", () => {
    const segments = segmentQueries<Row>([], flagsOf)
    expect(segments).toEqual({ newlySeen: [], newlyLost: [], opportunities: [], other: [] })
  })

  it("is total and non-overlapping across a larger randomized-shape set", () => {
    const rows: Row[] = Array.from({ length: 37 }, (_, i) => ({
      id: `row-${i}`,
      seen: i % 3 === 0,
      newlySeen: i % 7 === 0,
      newlyLost: i % 11 === 0,
    }))

    const segments = segmentQueries(rows, flagsOf)
    const totalOut =
      segments.newlySeen.length +
      segments.newlyLost.length +
      segments.opportunities.length +
      segments.other.length
    expect(totalOut).toBe(rows.length)

    const seenIds = new Set(
      [...segments.newlySeen, ...segments.newlyLost, ...segments.opportunities, ...segments.other].map(
        (r) => r.id,
      ),
    )
    expect(seenIds.size).toBe(rows.length)
  })
})

describe("segmentQueries — segment assignment rules", () => {
  it("puts a newly-seen item in newlySeen even though it is currently seen", () => {
    const segments = segmentQueries([{ id: "a", seen: true, newlySeen: true }], flagsOf)
    expect(segments.newlySeen).toHaveLength(1)
    expect(segments.newlyLost).toHaveLength(0)
    expect(segments.opportunities).toHaveLength(0)
    expect(segments.other).toHaveLength(0)
  })

  it("puts a newly-lost item in newlyLost even though it is currently unseen", () => {
    const segments = segmentQueries([{ id: "a", seen: false, newlyLost: true }], flagsOf)
    expect(segments.newlyLost).toHaveLength(1)
    expect(segments.newlySeen).toHaveLength(0)
    expect(segments.opportunities).toHaveLength(0)
    expect(segments.other).toHaveLength(0)
  })

  it("puts an unseen item with no change signal in opportunities", () => {
    const segments = segmentQueries([{ id: "a", seen: false }], flagsOf)
    expect(segments.opportunities).toHaveLength(1)
  })

  it("puts a seen item with no change signal in other", () => {
    const segments = segmentQueries([{ id: "a", seen: true }], flagsOf)
    expect(segments.other).toHaveLength(1)
  })

  it("treats omitted newlySeen/newlyLost as false, not as an error", () => {
    const segments = segmentQueries(
      [{ id: "a", seen: true } as Row, { id: "b", seen: false } as Row],
      flagsOf,
    )
    expect(segments.other.map((r) => r.id)).toEqual(["a"])
    expect(segments.opportunities.map((r) => r.id)).toEqual(["b"])
  })

  it("resolves conflicting flags with newlySeen taking priority over newlyLost", () => {
    const segments = segmentQueries(
      [{ id: "a", seen: true, newlySeen: true, newlyLost: true }],
      flagsOf,
    )
    expect(segments.newlySeen).toHaveLength(1)
    expect(segments.newlyLost).toHaveLength(0)
  })

  it("preserves input order within each segment", () => {
    const rows: Row[] = [
      { id: "a", seen: false },
      { id: "b", seen: false },
      { id: "c", seen: false },
    ]
    const segments = segmentQueries(rows, flagsOf)
    expect(segments.opportunities.map((r) => r.id)).toEqual(["a", "b", "c"])
  })
})

describe("segmentQueries — purity", () => {
  it("does not mutate the input array or its items", () => {
    const rows: Row[] = [{ id: "a", seen: false }]
    const snapshot = JSON.parse(JSON.stringify(rows))
    segmentQueries(rows, flagsOf)
    expect(rows).toEqual(snapshot)
  })

  it("is deterministic — same input always produces an equal result", () => {
    const rows: Row[] = [
      { id: "a", seen: true, newlySeen: true },
      { id: "b", seen: false },
      { id: "c", seen: true },
    ]
    const first = segmentQueries(rows, flagsOf)
    const second = segmentQueries(rows, flagsOf)
    expect(first).toEqual(second)
  })

  it("never calls getFlags for items outside the input (no hidden inference)", () => {
    const rows: Row[] = [{ id: "a", seen: true }, { id: "b", seen: false }]
    let calls = 0
    segmentQueries(rows, (row) => {
      calls += 1
      return flagsOf(row)
    })
    expect(calls).toBe(rows.length)
  })
})
