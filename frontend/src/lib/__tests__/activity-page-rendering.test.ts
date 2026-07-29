import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  getActivityLog: vi.fn(),
  getWorkLog: vi.fn(),
}))

vi.mock("@/lib/api", () => api)
vi.mock("@/app/(admin)/clients/[id]/activity/WorkLogCard", () => ({
  WorkLogCard: () => null,
}))

import ActivityPage from "@/app/(admin)/clients/[id]/activity/page"

describe("ActivityPage note presentation", () => {
  it("renders historical notes without legacy or banned wording", async () => {
    api.getActivityLog.mockResolvedValue([{
      id: "activity-1",
      client_id: "client-1",
      event_type: "scan_completed",
      note: "Scan completed. AI Citability: 40. Overall GEO score: 51. "
        + "Brand was mentioned; citation rate was 20%.",
      created_at: "2026-07-29T00:00:00Z",
    }])
    api.getWorkLog.mockResolvedValue([])

    const element = await ActivityPage({
      params: Promise.resolve({ id: "client-1" }),
      searchParams: Promise.resolve({}),
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain(
      "Scan completed. AI Citability: 40. Growth Readiness: 51. "
        + "Brand was seen by AI; visibility frequency was 20%.",
    )
    expect(markup).not.toMatch(/Overall GEO score|\bmentioned\b|citation rate/i)
  })
})
