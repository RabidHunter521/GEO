import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"

const viewApi = vi.hoisted(() => ({
  getViewIssues: vi.fn(),
  getViewProgress: vi.fn(),
  getViewTruthHealth: vi.fn(),
}))

vi.mock("@/lib/view-api", () => viewApi)

import ViewReputationPage from "@/app/view/[token]/reputation/page"

describe("public reputation truth health", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    viewApi.getViewIssues.mockResolvedValue([])
    viewApi.getViewProgress.mockResolvedValue([])
    viewApi.getViewTruthHealth.mockResolvedValue({
      locations: [{
        name: "Orchard Clinic",
        city: "Singapore",
        hours_summary: "Mon–Fri: 09:00–17:00; Sat–Sun: Closed",
        service_categories: ["Dental implants", "Emergency care"],
      }, {
        name: "Tampines Clinic",
        city: "Singapore",
        hours_summary: null,
        service_categories: ["Emergency care"],
      }],
      fact_freshness: "2026-08-03T09:00:00Z",
      reviewed_open_issue_count: 1,
      corrected_count: 1,
      open_issues: [{
        summary: "A reviewed AI answer conflicts with verified business information.",
        status_label: "Open",
      }],
      resolved_issues: [{
        summary: "A reviewed AI answer conflicts with verified business information.",
        status_label: "Resolved",
      }],
    })
  })

  it("renders approved information and reviewed accuracy health without an alarm for candidates", async () => {
    const element = await ViewReputationPage({
      params: Promise.resolve({ token: "share-token" }),
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain("Accuracy Health")
    expect(markup).toContain("Verified business information")
    expect(markup).toContain("Orchard Clinic")
    expect(markup).toContain("Tampines Clinic")
    expect(markup).toContain('aria-label="Location selector"')
    expect(markup).toContain("Dental implants")
    expect(markup).toContain("reviewed issue open")
    expect(markup).toContain("corrective action awaiting proof")
    expect(markup).toContain("Resolved issues")
    expect(markup).not.toContain("Draft")
    expect(markup).not.toContain("candidate")
  })

  it("renders a reviewer-verified resolution even when no other reputation data exists", async () => {
    viewApi.getViewTruthHealth.mockResolvedValue({
      locations: [],
      fact_freshness: null,
      reviewed_open_issue_count: 0,
      corrected_count: 0,
      open_issues: [],
      resolved_issues: [{
        summary: "A reviewed AI answer conflicts with verified business information.",
        status_label: "Resolved",
      }],
    })

    const element = await ViewReputationPage({
      params: Promise.resolve({ token: "share-token" }),
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain("Resolved issues")
    expect(markup).toContain("Resolved.")
    expect(markup).not.toContain("No reputation issues flagged yet")
  })
})
