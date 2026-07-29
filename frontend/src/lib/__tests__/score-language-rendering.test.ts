import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"

const adminApi = vi.hoisted(() => ({
  getActionRecommendations: vi.fn(),
  getClient: vi.fn(),
  getGuarantee: vi.fn(),
  getIndustryBenchmark: vi.fn(),
  getLatestGeoScore: vi.fn(),
  getTrafficHistory: vi.fn(),
}))

const viewApi = vi.hoisted(() => ({
  getViewActions: vi.fn(),
  getViewIssues: vi.fn(),
  getViewOverview: vi.fn(),
  getViewProgress: vi.fn(),
  getViewScan: vi.fn(),
}))

vi.mock("@/lib/api", () => adminApi)
vi.mock("@/lib/view-api", () => viewApi)
vi.mock("@/app/(admin)/clients/actions", () => ({
  createGuaranteeAction: vi.fn(),
  resolveGuaranteeAction: vi.fn(),
}))
vi.mock("@/app/(admin)/clients/[id]/actions", () => ({
  markActionDismissed: vi.fn(),
  markActionDone: vi.fn(),
}))

import ClientOverviewPage from "@/app/(admin)/clients/[id]/page"
import ViewOverviewPage from "@/app/view/[token]/page"
import { ScoreHistoryChart } from "@/components/view/ScoreHistoryChart"

const score = {
  overall_score: 61,
  ai_visibility: 55,
  ai_citability: 55,
  brand_authority: 60,
  content_quality: 65,
  technical_foundations: 100,
  structured_data: 0,
  computed_at: "2026-07-29T00:00:00Z",
  brand_authority_evidence: [],
  content_quality_evidence: [],
}

describe("rendered Growth Readiness language", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    viewApi.getViewActions.mockResolvedValue([])
    viewApi.getViewIssues.mockResolvedValue([])
    viewApi.getViewProgress.mockResolvedValue([])
    viewApi.getViewScan.mockResolvedValue({ completed_at: score.computed_at, results: [] })
    adminApi.getActionRecommendations.mockResolvedValue([])
    adminApi.getGuarantee.mockResolvedValue(null)
    adminApi.getIndustryBenchmark.mockResolvedValue(null)
    adminApi.getTrafficHistory.mockResolvedValue([])
  })

  it("renders the public composite as Growth Readiness, separate from AI Presence", async () => {
    viewApi.getViewOverview.mockResolvedValue({
      profile: {
        name: "Example Co",
        website: "https://example.com",
        industry: "Healthcare",
        logo_url: null,
        is_prospect: false,
      },
      latest_score: score,
      platforms: [],
      benchmark: null,
      score_history: [],
      traffic: [],
      traffic_value: null,
      change_narrative: null,
      change_narrative_period: null,
      has_our_work: false,
      has_content_plan: false,
      has_progress: false,
      has_work_log: false,
      improvements_last_30d: 0,
      fixed_this_month: 0,
      last_checked_at: score.computed_at,
      next_check_due: null,
      is_stale: false,
      proof_cards: [],
      causal_trend: null,
      commitment: {
        metric_label: "Growth Readiness",
        baseline: 45,
        target: 60,
        current: 51,
        deadline: "2026-10-01",
        state: "in_progress",
      },
    })

    const element = await ViewOverviewPage({
      params: Promise.resolve({ token: "share-token" }),
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain("Your Growth Readiness")
    expect(markup).toContain("AI Presence")
    expect(markup).toContain("lifting your growth readiness")
    expect(markup).not.toMatch(/AI Visibility Score|How visible you are across AI search|overall score/i)
  })

  it("renders the admin composite as Growth Readiness instead of AI visibility", async () => {
    adminApi.getClient.mockResolvedValue({
      id: "client-1",
      name: "Example Co",
      website: "https://example.com",
      industry: "Healthcare",
      scan_cadence_days: 30,
    })
    adminApi.getLatestGeoScore.mockResolvedValue({
      id: "score-1",
      client_id: "client-1",
      scan_id: "scan-1",
      ...score,
      platform_breakdown: null,
    })

    const element = await ClientOverviewPage({
      params: Promise.resolve({ id: "client-1" }),
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain("Growth Readiness")
    expect(markup).toContain("AI Presence")
    expect(markup).not.toMatch(/How visible this client is across AI search/i)
  })

  it("gives score history a Growth Readiness name for sighted and screen-reader users", () => {
    const markup = renderToStaticMarkup(createElement(ScoreHistoryChart, {
      points: [
        { overall_score: 45, computed_at: "2026-07-01T00:00:00Z" },
        { overall_score: 61, computed_at: "2026-07-29T00:00:00Z" },
      ],
    }))

    expect(markup).toContain("Your Growth Readiness over time")
    expect(markup).toContain('aria-label="Growth Readiness history"')
    expect(markup).not.toMatch(/Visibility score history|Your score over time/i)
  })
})
