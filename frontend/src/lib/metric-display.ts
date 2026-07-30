// frontend/src/lib/metric-display.ts
// Pure formatting decisions for OutcomeMetricCard. `value`/`delta` on a
// Command Center metric are nullable — null means "nothing stored yet" and
// must render as an honest "—"/no-delta, never a fabricated 0. This module
// exists so that invariant has a contract test that doesn't require
// rendering React (see src/lib/__tests__/metric-display.test.ts).
import { getScoreColor, type ScoreColor } from "@/lib/score-utils"

export type MetricVariant = "score" | "count"

export interface FormattedValue {
  display: string
  // Non-null only for variant "score" — count metrics (e.g. AI-referral
  // visitors) are never color-banded.
  color: ScoreColor | null
}

// value === null (not a falsy check) is deliberate: a stored 0 is a real,
// reportable measurement and must render as "0", not as "no data".
export function formatMetricValue(value: number | null, variant: MetricVariant): FormattedValue {
  if (value === null) {
    return { display: "—", color: null }
  }
  return {
    display: Math.round(value).toLocaleString(),
    color: variant === "score" ? getScoreColor(value) : null,
  }
}

export type DeltaDirection = "up" | "down" | "flat"

export interface FormattedDelta {
  // Sign-prefixed magnitude only — callers append any unit suffix
  // (e.g. "pts", "visitors") themselves, matching the existing component.
  display: string
  direction: DeltaDirection
}

// delta === null (not a falsy check) is deliberate: a real delta of exactly
// 0 is "no change" — a fact worth showing — while null means "no prior
// period to compare against" and must render nothing at all.
export function formatMetricDelta(delta: number | null, variant: MetricVariant): FormattedDelta | null {
  if (delta === null) {
    return null
  }
  if (delta === 0) {
    // Exactly flat: no "+" prefix and no upward-trend framing — "+0.0"
    // reads as positive movement when there was none.
    return { display: variant === "count" ? "0" : "0.0", direction: "flat" }
  }
  const magnitude = variant === "count" ? Math.round(delta).toLocaleString() : delta.toFixed(1)
  return {
    display: delta > 0 ? `+${magnitude}` : magnitude,
    direction: delta > 0 ? "up" : "down",
  }
}
