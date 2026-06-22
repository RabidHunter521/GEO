// frontend/src/lib/client-list-utils.ts
// Pure portfolio logic for the /clients overview: score deltas, the
// needs-attention queue, and client-side list filtering. Keeps ClientsManager
// thin and the product thresholds in one place.
import type { ClientListItem, ScoreBand } from "@/types"
import { getScoreBand } from "@/lib/score-utils"

// Product thresholds — mirror the ±5pt digest rule and the 30-day report cadence.
export const ATTENTION_SCORE_DROP_PTS = 5
export const ATTENTION_STALE_DAYS = 30

export type AttentionReason =
  | "score_drop"
  | "low_score"
  | "scan_failed"
  | "stale"
  | "never_scanned"

export const ATTENTION_LABELS: Record<AttentionReason, string> = {
  score_drop: "Score dropped",
  low_score: "Low score",
  scan_failed: "Last scan failed",
  stale: `No scan in ${ATTENTION_STALE_DAYS}+ days`,
  never_scanned: "Never scanned",
}

export function scoreDelta(c: ClientListItem): number | null {
  if (c.latest_overall_score === null || c.previous_overall_score === null) return null
  return c.latest_overall_score - c.previous_overall_score
}

function daysSince(iso: string, now: Date): number {
  return (now.getTime() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24)
}

export function attentionReasons(c: ClientListItem, now: Date): AttentionReason[] {
  const reasons: AttentionReason[] = []
  const delta = scoreDelta(c)
  if (delta !== null && delta <= -ATTENTION_SCORE_DROP_PTS) reasons.push("score_drop")
  if (c.latest_overall_score !== null && getScoreBand(c.latest_overall_score).name === "low") {
    reasons.push("low_score")
  }
  if (c.latest_scan_status === "failed") reasons.push("scan_failed")
  if (c.last_scan_at === null && c.latest_scan_status === null) {
    reasons.push("never_scanned")
  } else if (c.last_scan_at !== null && daysSince(c.last_scan_at, now) > ATTENTION_STALE_DAYS) {
    reasons.push("stale")
  }
  return reasons
}

export type BandFilter = "all" | ScoreBand["name"] | "none"
export type RecencyFilter = "all" | "7d" | "30d" | "never"

export interface ClientFilters {
  band: BandFilter
  industry: string // "all" or exact industry value
  country: string // "all", "none" (not set) or exact country value
  recency: RecencyFilter
  scanDue: boolean
}

export const DEFAULT_FILTERS: ClientFilters = {
  band: "all",
  industry: "all",
  country: "all",
  recency: "all",
  scanDue: false,
}

export function hasActiveFilters(f: ClientFilters): boolean {
  return f.band !== "all" || f.industry !== "all" || f.country !== "all" || f.recency !== "all" || f.scanDue
}

export function applyFilters(
  clients: ClientListItem[],
  f: ClientFilters,
  now: Date,
): ClientListItem[] {
  return clients.filter((c) => {
    if (f.band !== "all") {
      if (f.band === "none") {
        if (c.latest_overall_score !== null) return false
      } else if (
        c.latest_overall_score === null ||
        getScoreBand(c.latest_overall_score).name !== f.band
      ) {
        return false
      }
    }
    if (f.industry !== "all" && c.industry !== f.industry) return false
    if (f.country !== "all") {
      if (f.country === "none") {
        if (c.country !== null && c.country !== "") return false
      } else if (c.country !== f.country) {
        return false
      }
    }
    if (f.recency !== "all") {
      // last_scan_at = last successful scan; failed scans don't refresh it
      if (f.recency === "never") {
        if (c.last_scan_at !== null) return false
      } else {
        const windowDays = f.recency === "7d" ? 7 : 30
        if (c.last_scan_at === null || daysSince(c.last_scan_at, now) > windowDays) return false
      }
    }
    if (f.scanDue && !c.is_scan_overdue) return false
    return true
  })
}
