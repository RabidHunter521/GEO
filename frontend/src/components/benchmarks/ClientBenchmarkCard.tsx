// frontend/src/components/benchmarks/ClientBenchmarkCard.tsx
// Client-facing cohort comparison (Phase 6 Task 6).
//
// Replaces IndustryBenchmarkCard on the share view wherever an approved
// snapshot exists. Three things it deliberately never does:
//
//   - name a competitor, or imply the cohort is the client's competitive set;
//   - show an exact peer count or a rank (the legacy card shows both);
//   - render a number beside a withheld comparison.
//
// It leads with the position band and one next action, and puts methodology
// behind a <details> disclosure so the card stays readable on a phone.
import { Trophy } from "lucide-react"

import {
  formatMetricValue,
  nextActionFor,
  percentileBandLabel,
  percentileBandSymbol,
  rangeLabel,
  suppressionText,
} from "@/lib/benchmark-display"
import type { BenchmarkComparisonPublic } from "@/types"

export function ClientBenchmarkCard({
  comparisons,
}: {
  comparisons: BenchmarkComparisonPublic[]
}) {
  if (comparisons.length === 0) return null

  const period = comparisons[0]
  const published = comparisons.filter((item) => !item.suppressed)
  const withheld = comparisons.filter((item) => item.suppressed)

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-start gap-3">
        <Trophy className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium">How you compare</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {period.cohort_label} · {period.period_start} to {period.period_end}
          </p>

          {published.length > 0 && (
            <ul className="mt-3 space-y-3">
              {published.map((item) => {
                const band = percentileBandLabel(item.percentile_band)
                const action = nextActionFor(item)
                return (
                  <li key={item.metric_key}>
                    <p className="text-sm font-medium">
                      <span aria-hidden="true" className="mr-1">
                        {percentileBandSymbol(item.percentile_band)}
                      </span>
                      {item.metric_label}: {band}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      You: {formatMetricValue(item.client_value, item.metric_key)} · comparable
                      businesses: {rangeLabel(item)} · {item.member_count_band} businesses
                    </p>
                    {action && <p className="mt-1 text-xs">{action}</p>}
                  </li>
                )
              })}
            </ul>
          )}

          {withheld.length > 0 && (
            <ul className="mt-3 space-y-1">
              {withheld.map((item) => (
                <li key={item.metric_key} className="text-xs text-muted-foreground">
                  <span className="font-medium">{item.metric_label}:</span>{" "}
                  {suppressionText(item)}
                </li>
              ))}
            </ul>
          )}

          <details className="mt-3">
            <summary className="cursor-pointer text-xs text-muted-foreground underline underline-offset-2">
              How this is measured
            </summary>
            <p className="mt-2 text-xs text-muted-foreground">
              {period.caveat} Comparable means SeenBy clients in the same industry, country,
              and size band, measured over the same period. Ranges are only published once a
              group is large enough that no individual business can be identified from them,
              which is why some measures are withheld. We never show you which businesses are
              in the group, and they never see you.
            </p>
          </details>
        </div>
      </div>
    </div>
  )
}
