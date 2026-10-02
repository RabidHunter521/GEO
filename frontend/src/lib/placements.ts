// Pure helpers for the placement engine UI (admin-only). Kept free of React so
// they are unit-tested directly.
import type { PlacementCategory, PlacementEmailDraft, PlacementStatus, PlacementTarget, Platform } from "@/types"

export const PLACEMENT_STATUS_LABEL: Record<PlacementStatus, string> = {
  open: "Open",
  pursuing: "Pursuing",
  placed: "Placed",
  verified: "Verified",
  stale: "Stale",
  dismissed: "Dismissed",
}

export const PLACEMENT_CATEGORY_LABEL: Record<PlacementCategory, string> = {
  listicle: "Listicle",
  directory: "Directory",
  news: "News",
  review: "Review site",
  social: "Social",
  marketplace: "Marketplace",
  reference: "Reference",
  other: "Other",
}

export type StatusFilter = "active" | PlacementStatus

export interface PlacementFilters {
  status: StatusFilter
  category: PlacementCategory | "all"
  platform: Platform | "all"
}

export const DEFAULT_FILTERS: PlacementFilters = { status: "active", category: "all", platform: "all" }

// "active" = everything still worth a look: not dismissed, not stale, and not
// an open page that already names the client (nothing left to win there).
export function filterPlacements(targets: PlacementTarget[], f: PlacementFilters): PlacementTarget[] {
  return targets.filter((t) => {
    if (f.status === "active") {
      if (t.status === "dismissed" || t.status === "stale") return false
      if (t.status === "open" && t.client_present) return false
    } else if (t.status !== f.status) {
      return false
    }
    if (f.category !== "all" && t.category !== f.category) return false
    if (f.platform !== "all" && !t.platforms.includes(f.platform)) return false
    return true
  })
}

export function mailtoHref(draft: Pick<PlacementEmailDraft, "to" | "subject" | "body">): string {
  const to = draft.to.map(encodeURIComponent).join(",")
  return `mailto:${to}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}`
}

export function scoreTone(score: number): "high" | "medium" | "low" {
  return score >= 60 ? "high" : score >= 30 ? "medium" : "low"
}
