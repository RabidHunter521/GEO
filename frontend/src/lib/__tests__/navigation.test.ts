import { describe, expect, it } from "vitest"
import { ADMIN_GLOBAL_NAV, CLIENT_NAV_GROUPS, isNavItemActive } from "../navigation"

describe("navigation contract", () => {
  it("groups client nav into six outcome-led sections", () => {
    expect(CLIENT_NAV_GROUPS.map((group) => group.label)).toEqual([
      "Intelligence",
      "Reputation",
      "Growth",
      "Delivery",
      "Proof",
      "Setup",
    ])
  })

  it("keeps every legacy client sub-route reachable somewhere in the groups", () => {
    const hrefs = CLIENT_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.href))
    expect(hrefs).toContain("/content-roadmap")
    expect(hrefs).toEqual([
      "/scan",
      "/competitors",
      "/toolkit",
      "/authority",
      "/reputation/truth",
      "/content-gaps",
      "/content-roadmap",
      "/content-studio",
      "/delivery",
      "/checklist",
      "/activity",
      "/reports",
      "/settings",
    ])
  })

  it("exposes the global (non-client-scoped) admin destinations", () => {
    expect(ADMIN_GLOBAL_NAV.map((item) => item.href)).toEqual([
      "/dashboard",
      "/clients",
      "/gap-matrix",
      "/benchmarks",
      "/review-queue",
    ])
  })

  it("marks a client sub-route active when the pathname matches", () => {
    expect(isNavItemActive("/clients/abc/scan", "abc", "/scan")).toBe(true)
  })

  it("does not mark a nav item active for a different client or a different route", () => {
    expect(isNavItemActive("/clients/abc/scan", "abc", "/competitors")).toBe(false)
    expect(isNavItemActive("/clients/abc/scan", "xyz", "/scan")).toBe(false)
  })

  it("treats the ungrouped overview item as an exact match on the client root", () => {
    expect(isNavItemActive("/clients/abc", "abc", "")).toBe(true)
    expect(isNavItemActive("/clients/abc/scan", "abc", "")).toBe(false)
  })
})
