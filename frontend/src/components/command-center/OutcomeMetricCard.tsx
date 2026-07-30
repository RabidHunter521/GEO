// frontend/src/components/command-center/OutcomeMetricCard.tsx
// One headline number from the admin Command Center: label, value, delta,
// and the evidence behind it. `metric.value` is nullable — render an honest
// "—" rather than a fabricated 0 when there is nothing stored yet.
import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { formatMetricDelta, formatMetricValue, type DeltaDirection } from "@/lib/metric-display"
import { cn } from "@/lib/utils"
import type { MetricValue } from "@/types"

const SCORE_COLOR_CLASS: Record<string, string> = {
  green: "text-score-strong",
  yellow: "text-score-watch",
  red: "text-score-low",
}

const DELTA_COLOR_CLASS: Record<DeltaDirection, string> = {
  up: "text-score-strong",
  down: "text-score-watch",
  flat: "text-muted-foreground/70",
}

const DELTA_ICON: Record<DeltaDirection, typeof TrendingUp> = {
  up: TrendingUp,
  down: TrendingDown,
  flat: Minus,
}

interface Props {
  label: string
  metric: MetricValue
  // "score": 0-100 value, color-banded via getScoreColor (getScoreColor is a
  // generic 0-100 traffic light — applying it to a corrected-rate percentage
  // is the same banding used everywhere else a 0-100 number is shown).
  // "count": a raw tally (e.g. AI-referral visitors) — no color banding.
  variant: "score" | "count"
  // Appended to the formatted value, e.g. "%" for a percentage metric.
  unit?: string
  // Appended to the formatted delta, e.g. "pts" or "visitors".
  deltaUnit?: string
}

export function OutcomeMetricCard({ label, metric, variant, unit = "", deltaUnit = "" }: Props) {
  const { value, delta, evidence_label } = metric
  const formattedValue = formatMetricValue(value, variant)
  const formattedDelta = value === null ? null : formatMetricDelta(delta, variant)
  const DeltaIcon = formattedDelta ? DELTA_ICON[formattedDelta.direction] : null

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/60">{label}</p>
      {value === null ? (
        <p className="mt-2 font-display text-2xl font-semibold text-muted-foreground">—</p>
      ) : (
        <p
          className={cn(
            "mt-2 font-display text-2xl font-bold tabular-nums",
            formattedValue.color ? SCORE_COLOR_CLASS[formattedValue.color] : "text-foreground",
          )}
        >
          {formattedValue.display}
          {unit}
        </p>
      )}
      {formattedDelta && DeltaIcon && (
        <p
          className={cn(
            "mt-1 flex items-center gap-1 text-xs font-semibold",
            DELTA_COLOR_CLASS[formattedDelta.direction],
          )}
        >
          <DeltaIcon className="h-3.5 w-3.5" />
          {formattedDelta.display}
          {deltaUnit ? ` ${deltaUnit}` : ""}
        </p>
      )}
      <p className="mt-2 text-xs text-muted-foreground/70">{evidence_label}</p>
    </div>
  )
}
