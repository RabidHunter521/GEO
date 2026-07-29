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
  deleteCompetitorAction: vi.fn(),
  toggleControlQueryAction: vi.fn(),
}))

vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: { children: React.ReactNode }) => children,
  PopoverContent: ({ children }: { children: React.ReactNode }) => children,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => children,
}))

import { SettingsForm } from "@/app/(admin)/clients/[id]/settings/SettingsForm"
import type { Client } from "@/types"

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
  it("renders the score-drop help with the approved AI visibility label", () => {
    const markup = renderToStaticMarkup(createElement(SettingsForm, {
      client,
      competitors: [],
      trafficHistory: [],
      controlQueries: [],
    }))

    expect(markup).toContain("Alert fires when the AI visibility score drops below this number.")
    expect(markup).not.toContain("Overall GEO Score")
  })
})
