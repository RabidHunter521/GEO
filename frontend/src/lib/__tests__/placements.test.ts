import { describe, expect, it } from "vitest"
import type { PlacementTarget } from "@/types"
import { DEFAULT_FILTERS, filterPlacements, mailtoHref, scoreTone } from "../placements"

const target = (over: Partial<PlacementTarget>): PlacementTarget => ({
  id: "t", url: "https://x.example/a", domain: "x.example", title: null, category: "listicle",
  status: "open", answers_count: 1, platforms: ["chatgpt"], query_categories: ["recommendation"],
  competitors: [], other_businesses_listed: null, client_present: false, priority_score: 50,
  priority_reasons: [], authority_asset_id: null, outcome_action_id: null, last_seen_at: null,
  analyzed_at: null, ...over,
})

describe("filterPlacements", () => {
  it("active hides dismissed, stale, and open pages that already name the client", () => {
    const rows = [
      target({ id: "open" }),
      target({ id: "pursuing", status: "pursuing" }),
      target({ id: "placed", status: "placed", client_present: true }),
      target({ id: "dismissed", status: "dismissed" }),
      target({ id: "stale", status: "stale" }),
      target({ id: "already-there", client_present: true }),
    ]
    expect(filterPlacements(rows, DEFAULT_FILTERS).map((t) => t.id)).toEqual(["open", "pursuing", "placed"])
  })

  it("filters by exact status, category and platform", () => {
    const rows = [
      target({ id: "a", category: "directory", platforms: ["gemini"] }),
      target({ id: "b", category: "listicle", platforms: ["chatgpt", "gemini"] }),
      target({ id: "c", status: "dismissed", category: "listicle" }),
    ]
    expect(filterPlacements(rows, { status: "active", category: "listicle", platform: "gemini" })
      .map((t) => t.id)).toEqual(["b"])
    expect(filterPlacements(rows, { status: "dismissed", category: "all", platform: "all" })
      .map((t) => t.id)).toEqual(["c"])
  })
})

describe("mailtoHref", () => {
  it("encodes recipients, subject and body", () => {
    expect(mailtoHref({ to: ["editor@x.example"], subject: "Hi & hello", body: "Line 1\nLine 2" }))
      .toBe("mailto:editor%40x.example?subject=Hi%20%26%20hello&body=Line%201%0ALine%202")
  })
})

describe("scoreTone", () => {
  it("bands scores like the delivery priority", () => {
    expect([scoreTone(60), scoreTone(59), scoreTone(30), scoreTone(29)]).toEqual(["high", "medium", "medium", "low"])
  })
})
