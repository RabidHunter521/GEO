import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/app/(admin)/clients/[id]/settings/actions", () => ({
  syncGa4TrafficAction: vi.fn(),
  updateClientAction: vi.fn(),
  updateTrafficAction: vi.fn(),
  uploadClientLogoAction: vi.fn(),
}))

vi.mock("@/app/(admin)/clients/actions", () => ({
  addCompetitorAction: vi.fn(),
  addControlQueryAction: vi.fn(),
  createGuaranteeAction: vi.fn(),
  deleteCompetitorAction: vi.fn(),
  resolveGuaranteeAction: vi.fn(),
  toggleControlQueryAction: vi.fn(),
}))

vi.mock("@/app/(admin)/clients/[id]/content-studio/actions", () => ({
  getPageAuditDetailAction: vi.fn(),
  runPageAuditAction: vi.fn(),
}))

vi.mock("@/app/(admin)/clients/[id]/content-gaps/actions", () => ({
  refreshContentGapsAction: vi.fn(),
  runContentAnalysisAction: vi.fn(),
}))

vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: { children: React.ReactNode }) => children,
  PopoverContent: ({ children }: { children: React.ReactNode }) => children,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => children,
}))

import { GuaranteeCard } from "@/app/(admin)/clients/[id]/GuaranteeCard"
import { ContentGapsClient } from "@/app/(admin)/clients/[id]/content-gaps/ContentGapsClient"
import { PageAuditsSection } from "@/app/(admin)/clients/[id]/content-studio/PageAuditsSection"
import { SettingsForm } from "@/app/(admin)/clients/[id]/settings/SettingsForm"
import type { Client, ContentAnalysis, GuaranteeProgress } from "@/types"

const client = {
  id: "client-1",
  name: "Example Co",
  website: "https://example.com",
  industry: "Healthcare",
  enabled_platforms: ["chatgpt"],
  score_drop_threshold: 35,
  scan_cadence_days: 30,
  brand_authority_score: 0,
  content_quality_score: 0,
  technical_foundations_verified: false,
  structured_data_verified: false,
  visitor_to_lead_pct: 2,
  lead_to_customer_pct: 20,
} as Client

describe("SettingsForm terminology", () => {
  it("renders Growth Readiness for the score threshold and traffic note", () => {
    const markup = renderToStaticMarkup(createElement(SettingsForm, {
      client,
      competitors: [],
      trafficHistory: [],
      controlQueries: [],
    }))

    expect(markup).toContain("Alert fires when Growth Readiness drops below this number.")
    expect(markup).toContain("does not affect Growth Readiness.")
    expect(markup).not.toMatch(/AI visibility score|GEO score/i)
  })
})

describe("rendered admin terminology", () => {
  it("labels a composite-score commitment as Growth Readiness", () => {
    const progress = {
      id: "guarantee-1",
      metric: "overall_score",
      baseline_value: 45,
      target_value: 60,
      start_date: "2026-07-01",
      deadline_date: "2026-10-01",
      status: "active",
      current_value: 50,
      points_needed: 15,
      points_gained: 5,
      days_total: 92,
      days_remaining: 64,
      state: "on_track",
    } satisfies GuaranteeProgress

    const markup = renderToStaticMarkup(createElement(GuaranteeCard, {
      clientId: "client-1",
      initialProgress: progress,
    }))

    expect(markup).toContain("Growth Readiness")
    expect(markup).not.toContain("Overall score")
  })

  it("describes page audits as separate from Growth Readiness", () => {
    const markup = renderToStaticMarkup(createElement(PageAuditsSection, {
      clientId: "client-1",
      initialAudits: [],
    }))

    expect(markup).toContain("Informational only — not part of Growth Readiness.")
    expect(markup).not.toMatch(/GEO score/i)
  })

  it("describes weak topic coverage without banned mention wording", () => {
    const analysis = {
      id: "analysis-1",
      client_id: "client-1",
      status: "completed",
      topics_json: [{ topic: "Dental implants", status: "weak" }],
      entities_json: [],
      suggested_content_json: [],
      entity_coverage_score: 0,
      content_metrics_json: {
        word_count: 100,
        h1_count: 1,
        faq_count: 0,
        blog_count: 0,
        schema_present: false,
      },
      content_quality_recommendation: null,
      pages_crawled: 1,
      analyzed_at: "2026-07-29T00:00:00Z",
    } satisfies ContentAnalysis

    const markup = renderToStaticMarkup(createElement(ContentGapsClient, {
      clientId: "client-1",
      initialAnalysis: analysis,
    }))

    expect(markup).toContain("Covered briefly — worth expanding.")
    expect(markup).not.toMatch(/\bmentioned\b/i)
  })
})
