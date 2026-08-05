/**
 * Presentation logic for benchmark comparisons.
 *
 * Kept out of the components so it is unit-testable in the `unit` vitest
 * project (node environment, `src/lib/__tests__`), which is this repo's
 * established pattern — see metric-display.ts and delivery-lifecycle.ts.
 *
 * Every function here answers a question the UI must not get wrong: is this
 * cell suppressed, is this snapshot too old to lead with, and does the phrase
 * we are about to render describe missing data or poor performance? Those are
 * different statements and the components must never blur them.
 */
import type { BenchmarkComparison } from "@/types"

/** A snapshot older than this is shown, but labelled as a past period. */
export const STALE_AFTER_DAYS = 75

export type BenchmarkCellState = "published" | "suppressed" | "no_client_value"

export function cellState(comparison: BenchmarkComparison): BenchmarkCellState {
  if (!comparison.suppressed) return "published"
  if (comparison.suppression_reason === "no_client_value") return "no_client_value"
  return "suppressed"
}

/**
 * Suppression always reads as absent data, never as a bad result.
 *
 * The backend already ships a plain-language `suppression_message`; this is
 * the fallback for an unrecognised reason code. It must stay neutral: an
 * unknown reason rendering as anything judgemental would be a claim we cannot
 * support.
 */
export function suppressionText(comparison: BenchmarkComparison): string {
  return comparison.suppression_message ?? "Not enough comparable data yet."
}

export const PERCENTILE_BAND_LABELS: Record<string, string> = {
  top_quartile: "Top quarter",
  middle_half: "Middle half",
  bottom_quartile: "Bottom quarter",
}

export function percentileBandLabel(band: string | null | undefined): string | null {
  if (!band) return null
  return PERCENTILE_BAND_LABELS[band] ?? null
}

/**
 * Non-colour status cue, required by the program's accessibility rules: the
 * band must be readable without relying on the colour of the chip.
 */
export function percentileBandSymbol(band: string | null | undefined): string {
  if (band === "top_quartile") return "▲"
  if (band === "bottom_quartile") return "▼"
  return "—"
}

export function isStale(periodEnd: string, today: Date = new Date()): boolean {
  const end = new Date(`${periodEnd}T00:00:00Z`)
  if (Number.isNaN(end.getTime())) return false
  const days = (today.getTime() - end.getTime()) / 86_400_000
  return days > STALE_AFTER_DAYS
}

/**
 * True when a set of comparisons mixes calculation versions.
 *
 * Two metrics computed under different formula versions must not be presented
 * as one consistent picture; the grid shows a notice instead of silently
 * blending them.
 */
export function hasVersionMismatch(comparisons: BenchmarkComparison[]): boolean {
  const versions = new Set(
    comparisons
      .filter((item) => !item.suppressed && item.calculation_version)
      .map((item) => item.calculation_version as string),
  )
  return versions.size > 1
}

export interface CohortHealth {
  total: number
  published: number
  suppressed: number
  /** 0–100, rounded. 0 when there is nothing to summarise. */
  suppressionRate: number
  /** True when nothing at all can be shown yet. */
  isEmpty: boolean
  /** True when every entry is suppressed — a real, expected early state. */
  allSuppressed: boolean
}

export function cohortHealth(comparisons: BenchmarkComparison[]): CohortHealth {
  const total = comparisons.length
  const published = comparisons.filter((item) => !item.suppressed).length
  const suppressed = total - published
  return {
    total,
    published,
    suppressed,
    suppressionRate: total === 0 ? 0 : Math.round((suppressed / total) * 100),
    isEmpty: total === 0,
    allSuppressed: total > 0 && published === 0,
  }
}

/**
 * Clients worth attention: published, and sitting in the bottom quarter of
 * their own cohort. Deliberately not "below average" — half of any cohort is
 * below its median by construction, and calling that an opportunity would
 * generate busywork for every client every month.
 */
export function opportunityMetrics(comparisons: BenchmarkComparison[]): BenchmarkComparison[] {
  return comparisons.filter(
    (item) => !item.suppressed && item.percentile_band === "bottom_quartile",
  )
}

/** Formats a metric value for display, respecting the metric's unit. */
export function formatMetricValue(
  value: number | null | undefined,
  metricKey: string,
): string {
  if (value === null || value === undefined) return "—"
  if (metricKey === "accuracy_rate" || metricKey === "verified_action_rate") {
    return `${Math.round(value * 100)}%`
  }
  if (metricKey === "share_of_source") return `${value.toFixed(1)}%`
  return String(Math.round(value))
}

/** "40 – 55 – 70" style range summary, or null when suppressed. */
export function rangeLabel(comparison: BenchmarkComparison): string | null {
  if (comparison.suppressed) return null
  const { p25, p50, p75, metric_key } = comparison
  if (p25 === null || p50 === null || p75 === null) return null
  return [p25, p50, p75].map((value) => formatMetricValue(value, metric_key)).join(" · ")
}
