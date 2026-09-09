import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { AiTrafficChart } from "@/components/view/AiTrafficChart"

function point(period: string, ai_visitors: number, source: string) {
  return { period, ai_visitors, source }
}

function render(points: ReturnType<typeof point>[]): string {
  return renderToStaticMarkup(createElement(AiTrafficChart, { points }))
}

describe("AI traffic chart provenance", () => {
  it("says hand-entered months were supplied by the client, not measured", () => {
    const markup = render([
      point("2026-05-01", 100, "manual"),
      point("2026-06-01", 140, "manual"),
    ])
    expect(markup).toContain("Figures you supplied, entered by the SeenBy team")
    expect(markup).toContain("not measured by SeenBy")
    // The old copy claimed every number was "tracked by the SeenBy team",
    // which read as measurement for months that were typed in by hand.
    expect(markup).not.toContain("tracked by the SeenBy team")
    // Hand-entered bars carry a visible marker, not just caption text.
    expect(markup).toContain("stroke-dasharray")
  })

  it("claims direct measurement only when every month is synced", () => {
    const markup = render([
      point("2026-05-01", 100, "ga4"),
      point("2026-06-01", 140, "ga4"),
    ])
    expect(markup).toContain("Synced directly from your website analytics.")
    expect(markup).not.toContain("stroke-dasharray")
  })

  it("counts the split when the series mixes synced and hand-entered months", () => {
    const markup = render([
      point("2026-04-01", 80, "manual"),
      point("2026-05-01", 100, "manual"),
      point("2026-06-01", 140, "ga4"),
    ])
    expect(markup).toContain("1 of these 3 months are synced")
    expect(markup).toContain("the other 2 were entered by the SeenBy team")
  })
})
