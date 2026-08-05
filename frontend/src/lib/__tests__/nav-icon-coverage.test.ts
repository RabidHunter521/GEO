import { describe, expect, it } from "vitest"

import { ADMIN_GLOBAL_NAV, CLIENT_NAV_GROUPS } from "@/lib/navigation"
import { CLIENT_NAV_ICONS, GLOBAL_NAV_ICONS } from "@/components/layout/Sidebar"

/**
 * A missing icon entry is not a compile error — `Icon` is `undefined` at
 * runtime and React throws "Element type is invalid" the moment Sidebar
 * tries to render it, taking down the whole page around it.
 *
 * This happened twice for real: Phase 2 added `/delivery` to
 * CLIENT_NAV_GROUPS without an icon, Phase 3 added `/reputation/truth` the
 * same way. Both sat undetected because the client detail page was already
 * failing for an unrelated backend reason, so nobody ever saw the sidebar
 * actually try to render them against live data. Once that backend issue was
 * fixed, both crashed the page immediately.
 */
describe("nav icon coverage", () => {
  it("has an icon for every global nav destination", () => {
    for (const item of ADMIN_GLOBAL_NAV) {
      expect(GLOBAL_NAV_ICONS[item.href], `missing icon for ${item.href}`).toBeDefined()
    }
  })

  it("has an icon for every client-scoped nav destination", () => {
    for (const group of CLIENT_NAV_GROUPS) {
      for (const item of group.items) {
        expect(CLIENT_NAV_ICONS[item.href], `missing icon for ${item.href}`).toBeDefined()
      }
    }
  })

  it("does not carry icon entries for routes nav no longer lists", () => {
    // A stale entry is harmless at runtime, but it's a sign the two lists
    // have drifted and is worth catching before it hides a real rename.
    const globalHrefs: Set<string> = new Set(ADMIN_GLOBAL_NAV.map((item): string => item.href))
    const clientHrefs: Set<string> = new Set(
      CLIENT_NAV_GROUPS.flatMap((group) => group.items.map((item): string => item.href)),
    )

    for (const href of Object.keys(GLOBAL_NAV_ICONS)) {
      expect(globalHrefs.has(href), `${href} has an icon but is not in ADMIN_GLOBAL_NAV`).toBe(true)
    }
    for (const href of Object.keys(CLIENT_NAV_ICONS)) {
      expect(clientHrefs.has(href), `${href} has an icon but is not in CLIENT_NAV_GROUPS`).toBe(true)
    }
  })
})
