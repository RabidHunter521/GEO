/**
 * Serializable admin navigation contract.
 *
 * This module deliberately holds no React/component values (icons, JSX) so it
 * stays plain data — Sidebar.tsx owns the icon associations. Every `href`
 * here is a presentation-level regrouping of existing routes; it must never
 * introduce a route that doesn't already exist under
 * `src/app/(admin)/clients/[id]/`.
 */

export interface NavItem {
  href: string
  label: string
}

export interface NavGroup {
  label: string
  items: readonly NavItem[]
}

/** Global (non-client-scoped) destinations, always reachable regardless of which client is open. */
export const ADMIN_GLOBAL_NAV: readonly NavItem[] = [
  { href: "/clients", label: "All Clients" },
  { href: "/gap-matrix", label: "Portfolio Intelligence" },
  // Phase 6. Global rather than client-scoped: it compares the whole portfolio
  // against cohorts, so it does not belong in CLIENT_NAV_GROUPS' Intelligence
  // group (those hrefs are relative to /clients/[id]).
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/review-queue", label: "Review Queue" },
] as const

/**
 * Client-scoped sub-routes, grouped by outcome rather than by feature area.
 * `href` values are relative to `/clients/[id]` and map 1:1 onto existing
 * routes — see CLAUDE.md section 9 for the canonical route list.
 */
export const CLIENT_NAV_GROUPS = [
  {
    label: "Intelligence",
    items: [
      { href: "/scan", label: "AI Presence" },
      { href: "/competitors", label: "Competitors" },
    ],
  },
  {
    label: "Reputation",
    items: [
      { href: "/toolkit", label: "Technical Foundations" },
      { href: "/authority", label: "Authority" },
      { href: "/reputation/truth", label: "Business Truth" },
    ],
  },
  {
    label: "Growth",
    items: [
      { href: "/content-gaps", label: "Opportunities" },
      { href: "/content-roadmap", label: "Content Plan" },
      { href: "/content-studio", label: "Content Production" },
    ],
  },
  {
    label: "Delivery",
    items: [
      { href: "/delivery", label: "Delivery" },
      { href: "/checklist", label: "Action Plan" },
      { href: "/activity", label: "Delivery & Progress" },
    ],
  },
  {
    label: "Proof",
    items: [{ href: "/reports", label: "Reports" }],
  },
  {
    label: "Setup",
    items: [{ href: "/settings", label: "Client Setup" }],
  },
] as const satisfies readonly NavGroup[]

/**
 * Whether a client sub-nav item should render as active for the current
 * pathname. `href === ""` is the ungrouped Overview item, which is the
 * client detail page itself (`/clients/[id]`) and matches only exactly.
 */
export function isNavItemActive(pathname: string, clientId: string, href: string): boolean {
  const base = `/clients/${clientId}`
  if (href === "") {
    return pathname === base
  }
  const target = `${base}${href}`
  return pathname === target || pathname.startsWith(`${target}/`)
}
