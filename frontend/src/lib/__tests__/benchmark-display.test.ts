import { describe, expect, it } from "vitest"

import {
  cellState,
  cohortHealth,
  formatMetricValue,
  hasVersionMismatch,
  isStale,
  nextActionFor,
  opportunityMetrics,
  percentileBandLabel,
  percentileBandSymbol,
  rangeLabel,
  suppressionText,
} from "@/lib/benchmark-display"
import type { BenchmarkComparison } from "@/types"

function comparison(overrides: Partial<BenchmarkComparison> = {}): BenchmarkComparison {
  return {
    metric_key: "ai_presence_score",
    metric_label: "Seen by AI",
    client_value: 72,
    percentile_band: "top_quartile",
    cohort_label: "Comparable SeenBy clients: single-location healthcare businesses in Kuala Lumpur",
    p25: 40,
    p50: 55,
    p75: 70,
    period_start: "2026-07-01",
    period_end: "2026-07-31",
    member_count_band: "10–19",
    calculation_version: "v1",
    suppressed: false,
    suppression_message: null,
    caveat: "Describes comparable SeenBy clients over this period.",
    ...overrides,
  }
}

describe("cellState", () => {
  it("reports a published comparison", () => {
    expect(cellState(comparison())).toBe("published")
  })

  it("separates a missing client value from a suppressed cohort", () => {
    const missing = comparison({ suppressed: true, suppression_reason: "no_client_value" })
    const suppressed = comparison({ suppressed: true, suppression_reason: "cohort_below_minimum" })

    expect(cellState(missing)).toBe("no_client_value")
    expect(cellState(suppressed)).toBe("suppressed")
  })
})

describe("suppressionText", () => {
  it("prefers the backend's plain-language message", () => {
    const item = comparison({
      suppressed: true,
      suppression_message: "Not enough comparable businesses yet to publish a range.",
    })
    expect(suppressionText(item)).toContain("Not enough comparable businesses")
  })

  it("falls back to a neutral phrase for an unknown reason", () => {
    const text = suppressionText(comparison({ suppressed: true, suppression_message: null }))
    expect(text).toBe("Not enough comparable data yet.")
  })

  it("never implies poor performance", () => {
    const judgemental = ["poor", "bad", "low", "behind", "failing", "worse"]
    const text = suppressionText(comparison({ suppressed: true, suppression_message: null }))
    for (const word of judgemental) {
      expect(text.toLowerCase()).not.toContain(word)
    }
  })
})

describe("percentile bands", () => {
  it("labels every band", () => {
    expect(percentileBandLabel("top_quartile")).toBe("Top quarter")
    expect(percentileBandLabel("middle_half")).toBe("Middle half")
    expect(percentileBandLabel("bottom_quartile")).toBe("Bottom quarter")
  })

  it("returns null rather than inventing a label", () => {
    expect(percentileBandLabel(null)).toBeNull()
    expect(percentileBandLabel("something_new")).toBeNull()
  })

  it("carries a non-colour cue for each band", () => {
    expect(percentileBandSymbol("top_quartile")).toBe("▲")
    expect(percentileBandSymbol("bottom_quartile")).toBe("▼")
    expect(percentileBandSymbol("middle_half")).toBe("—")
    expect(percentileBandSymbol(null)).toBe("—")
  })
})

describe("isStale", () => {
  it("treats a recently closed period as current", () => {
    expect(isStale("2026-07-31", new Date("2026-08-05T00:00:00Z"))).toBe(false)
  })

  it("flags a period that has fallen far behind", () => {
    expect(isStale("2026-01-31", new Date("2026-08-05T00:00:00Z"))).toBe(true)
  })

  it("does not crash on an unparseable date", () => {
    expect(isStale("not-a-date", new Date("2026-08-05T00:00:00Z"))).toBe(false)
  })
})

describe("hasVersionMismatch", () => {
  it("is false when every published entry shares a version", () => {
    expect(hasVersionMismatch([comparison(), comparison({ metric_key: "accuracy_rate" })])).toBe(
      false,
    )
  })

  it("is true when published entries disagree", () => {
    expect(
      hasVersionMismatch([comparison(), comparison({ calculation_version: "v2" })]),
    ).toBe(true)
  })

  it("ignores suppressed entries, which carry no comparable numbers", () => {
    const suppressed = comparison({ suppressed: true, calculation_version: "v9" })
    expect(hasVersionMismatch([comparison(), suppressed])).toBe(false)
  })
})

describe("cohortHealth", () => {
  it("summarises an empty state without dividing by zero", () => {
    const health = cohortHealth([])
    expect(health.isEmpty).toBe(true)
    expect(health.suppressionRate).toBe(0)
    expect(health.allSuppressed).toBe(false)
  })

  it("reports a fully suppressed portfolio as its own state", () => {
    const health = cohortHealth([
      comparison({ suppressed: true }),
      comparison({ suppressed: true }),
    ])
    expect(health.allSuppressed).toBe(true)
    expect(health.suppressionRate).toBe(100)
  })

  it("computes a suppression rate", () => {
    const health = cohortHealth([
      comparison(),
      comparison({ suppressed: true }),
      comparison({ suppressed: true }),
      comparison(),
    ])
    expect(health.published).toBe(2)
    expect(health.suppressed).toBe(2)
    expect(health.suppressionRate).toBe(50)
  })
})

describe("opportunityMetrics", () => {
  it("selects only the bottom quarter, not everything below the median", () => {
    const items = [
      comparison({ percentile_band: "bottom_quartile" }),
      comparison({ percentile_band: "middle_half" }),
      comparison({ percentile_band: "top_quartile" }),
    ]
    const opportunities = opportunityMetrics(items)
    expect(opportunities).toHaveLength(1)
    expect(opportunities[0].percentile_band).toBe("bottom_quartile")
  })

  it("never surfaces a suppressed entry as an opportunity", () => {
    const items = [comparison({ suppressed: true, percentile_band: "bottom_quartile" })]
    expect(opportunityMetrics(items)).toHaveLength(0)
  })
})

describe("formatMetricValue", () => {
  it("renders ratios as percentages", () => {
    expect(formatMetricValue(0.92, "accuracy_rate")).toBe("92%")
    expect(formatMetricValue(0.5, "verified_action_rate")).toBe("50%")
  })

  it("renders share of source with one decimal", () => {
    expect(formatMetricValue(12.34, "share_of_source")).toBe("12.3%")
  })

  it("renders scores as whole numbers", () => {
    expect(formatMetricValue(72.4, "ai_presence_score")).toBe("72")
  })

  it("renders an em dash for an absent value rather than a zero", () => {
    expect(formatMetricValue(null, "ai_presence_score")).toBe("—")
    expect(formatMetricValue(undefined, "ai_presence_score")).toBe("—")
  })
})

describe("nextActionFor", () => {
  it("offers an action only for the bottom quarter", () => {
    expect(nextActionFor(comparison({ percentile_band: "bottom_quartile" }))).toBeTruthy()
    expect(nextActionFor(comparison({ percentile_band: "middle_half" }))).toBeNull()
    expect(nextActionFor(comparison({ percentile_band: "top_quartile" }))).toBeNull()
  })

  it("never offers an action for a suppressed comparison", () => {
    const item = comparison({ suppressed: true, percentile_band: "bottom_quartile" })
    expect(nextActionFor(item)).toBeNull()
  })

  it("covers every metric in the registry", () => {
    const metrics = [
      "ai_presence_score",
      "answer_stability_score",
      "accuracy_rate",
      "share_of_source",
      "verified_action_rate",
    ]
    for (const metric_key of metrics) {
      const action = nextActionFor(comparison({ metric_key, percentile_band: "bottom_quartile" }))
      expect(action, metric_key).toBeTruthy()
    }
  })

  it("returns null for an unknown metric rather than inventing advice", () => {
    const item = comparison({ metric_key: "something_new", percentile_band: "bottom_quartile" })
    expect(nextActionFor(item)).toBeNull()
  })

  it("describes what we will do, never what the client will get", () => {
    const promises = ["guarantee", "will increase", "will improve", "ensure", "boost your"]
    for (const metric_key of ["ai_presence_score", "accuracy_rate", "share_of_source"]) {
      const action = nextActionFor(
        comparison({ metric_key, percentile_band: "bottom_quartile" }),
      ) as string
      for (const promise of promises) {
        expect(action.toLowerCase()).not.toContain(promise)
      }
    }
  })

  it("uses no banned CLAUDE.md section 2 vocabulary", () => {
    const banned = ["cited", "uncited", "citation rate", "ranking position", "visibility gap"]
    const metrics = [
      "ai_presence_score",
      "answer_stability_score",
      "accuracy_rate",
      "share_of_source",
      "verified_action_rate",
    ]
    for (const metric_key of metrics) {
      const action = nextActionFor(
        comparison({ metric_key, percentile_band: "bottom_quartile" }),
      ) as string
      for (const term of banned) {
        expect(action.toLowerCase()).not.toContain(term)
      }
    }
  })
})

describe("rangeLabel", () => {
  it("summarises the interquartile range", () => {
    expect(rangeLabel(comparison())).toBe("40 · 55 · 70")
  })

  it("returns null for a suppressed comparison", () => {
    expect(rangeLabel(comparison({ suppressed: true, p25: null, p50: null, p75: null }))).toBeNull()
  })
})
