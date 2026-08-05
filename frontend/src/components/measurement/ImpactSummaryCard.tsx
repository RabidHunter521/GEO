import type { ImpactSummary, ImpactSummaryPublic } from "@/types"
import { EvidenceLadder } from "./EvidenceLadder"

export function ImpactSummaryCard({
  summaries,
}: {
  summaries: (ImpactSummary | ImpactSummaryPublic)[]
}) {
  if (!summaries || summaries.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Business Impact Evidence
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          No conversion evidence recorded yet
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border bg-card p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Business Impact Evidence
      </p>
      <p className="mt-1 text-[10px] text-muted-foreground/60">
        Values are separated by evidence level
      </p>

      <div className="mt-4 space-y-6">
        {summaries.map((summary, i) => (
          <div key={`${summary.currency}-${i}`}>
            {summaries.length > 1 && (
              <p className="mb-2 text-xs font-semibold text-muted-foreground">
                {summary.currency}
              </p>
            )}
            <EvidenceLadder summary={summary} />
            {summary.window_start && summary.window_end && (
              <p className="mt-1 text-[10px] text-muted-foreground/60">
                Window: {summary.window_start} to {summary.window_end}
              </p>
            )}
          </div>
        ))}
      </div>

      {"calculation_version" in summaries[0] && (summaries[0] as ImpactSummary).calculation_version && (
        <p className="mt-3 text-[10px] text-muted-foreground/60">
          {(summaries[0] as ImpactSummary).calculation_version}
        </p>
      )}
    </div>
  )
}
