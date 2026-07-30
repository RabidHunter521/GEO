// frontend/src/components/command-center/OutcomeMetricCard.tsx
// One headline number from the admin Command Center: label, value, delta,
// and the evidence behind it. `metric.value` is nullable — render an honest
// "—" rather than a fabricated 0 when there is nothing stored yet.
import { TrendingUp, TrendingDown } from "lucide-react"
import { getScoreColor } from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type { MetricValue } from "@/types"

const SCORE_COLOR_CLASS: Record<string, string> = {
  green: "text-score-strong",
  yellow: "text-score-watch",
  red: "text-score-low",
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
  const color = variant === "score" && value !== null ? getScoreColor(value) : null

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/60">{label}</p>
      {value === null ? (
        <p className="mt-2 font-display text-2xl font-semibold text-muted-foreground">—</p>
      ) : (
        <p
          className={cn(
            "mt-2 font-display text-2xl font-bold tabular-nums",
            color ? SCORE_COLOR_CLASS[color] : "text-foreground",
          )}
        >
          {Math.round(value).toLocaleString()}
          {unit}
        </p>
      )}
      {value !== null && delta !== null && (
        <p
          className={cn(
            "mt-1 flex items-center gap-1 text-xs font-semibold",
            delta >= 0 ? "text-score-strong" : "text-score-watch",
          )}
        >
          {delta >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          {delta >= 0 ? "+" : ""}
          {variant === "count" ? Math.round(delta).toLocaleString() : delta.toFixed(1)}
          {deltaUnit ? ` ${deltaUnit}` : ""}
        </p>
      )}
      <p className="mt-2 text-xs text-muted-foreground/70">{evidence_label}</p>
    </div>
  )
}
