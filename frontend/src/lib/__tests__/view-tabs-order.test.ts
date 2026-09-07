import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("next/navigation", () => ({
  usePathname: () => "/view/tok",
  useRouter: () => ({ push: vi.fn() }),
}))

import { ViewTabs } from "@/components/view/ViewTabs"

// The desktop <nav> is the ordered tab row; the mobile <select> repeats the
// same labels, so assert order against the nav alone.
function navLabels(markup: string): string[] {
  const nav = markup.slice(markup.indexOf('aria-label="Sections"'))
  return [...nav.matchAll(/>([^<>]+)<\/a>/g)].map((m) => m[1].trim())
}

function render(props: Record<string, unknown>): string {
  return renderToStaticMarkup(createElement(ViewTabs, { token: "tok", ...props }))
}

describe("client view tab order and gating", () => {
  it("puts Progress directly after Overview — proof of work before diagnostics", () => {
    const markup = render({
      showProgress: true, showContentPlan: true, showReputation: true,
    })
    expect(navLabels(markup)).toEqual([
      "Overview", "Progress", "Visibility", "Reputation", "Action Plan", "Reports",
    ])
  })

  it("hides Reputation when there is no finding, so no tab opens onto an empty page", () => {
    const markup = render({
      showProgress: true, showContentPlan: true, showReputation: false,
    })
    expect(navLabels(markup)).toEqual([
      "Overview", "Progress", "Visibility", "Action Plan", "Reports",
    ])
    expect(markup).not.toContain("/view/tok/reputation")
  })

  it("drops Progress until work has been published, keeping Visibility second", () => {
    const markup = render({
      showProgress: false, showContentPlan: true, showReputation: true,
    })
    expect(navLabels(markup)).toEqual([
      "Overview", "Visibility", "Reputation", "Action Plan", "Reports",
    ])
  })

  it("still shows prospects only Overview and Visibility", () => {
    const markup = render({
      isProspect: true, showProgress: true, showContentPlan: true, showReputation: true,
    })
    expect(navLabels(markup)).toEqual(["Overview", "Visibility"])
  })
})
