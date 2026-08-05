import { cn } from "@/lib/utils"
import type { QueryStabilityEntry, StabilityState } from "@/types"

const STATE_CONFIG: Record<StabilityState, { label: string; color: string; bg: string }> = {
  stable:       { label: "Stable",            color: "text-score-strong", bg: "bg-score-strong-bg" },
  repeated:     { label: "Repeated",          color: "text-blue-600 dark:text-blue-400",    bg: "bg-blue-50 dark:bg-blue-950/30" },
  emerging:     { label: "Emerging",          color: "text-score-watch",  bg: "bg-score-watch-bg" },
  volatile:     { label: "Volatile",          color: "text-score-low",    bg: "bg-score-low-bg" },
  insufficient: { label: "Insufficient data", color: "text-muted-foreground", bg: "bg-muted" },
}

const STATE_ORDER: StabilityState[] = ["stable", "repeated", "emerging", "volatile", "insufficient"]

export function StabilityCard({
  entries,
}: {
  entries: QueryStabilityEntry[]
}) {
  if (!entries || entries.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Answer Stability
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Not enough sampling data yet
        </p>
      </div>
    )
  }

  const counts: Record<StabilityState, number> = {
    stable: 0, repeated: 0, emerging: 0, volatile: 0, insufficient: 0,
  }
  for (const entry of entries) {
    counts[entry.state] = (counts[entry.state] || 0) + 1
  }

  const total = entries.length
  const version = entries[0]?.calculation_version ?? "stability_v1"

  return (
    <div className="rounded-xl border bg-card p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Answer Stability
      </p>
      <p className="mt-2 text-sm text-foreground">
        <span className="font-semibold tabular-nums">{total}</span>{" "}
        {total === 1 ? "query" : "queries"} tracked
        {STATE_ORDER.filter((s) => counts[s] > 0).map((s) => {
          const cfg = STATE_CONFIG[s]
          return (
            <span key={s} className="ml-2">
              &middot;{" "}
              <span className={cn("font-semibold tabular-nums", cfg.color)}>
                {counts[s]}
              </span>{" "}
              {cfg.label.toLowerCase()}
            </span>
          )
        })}
      </p>

      {/* Visual bar */}
      <div className="mt-3 flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
        {STATE_ORDER.filter((s) => counts[s] > 0).map((s) => {
          const pct = (counts[s] / total) * 100
          const cfg = STATE_CONFIG[s]
          return (
            <div
              key={s}
              className={cn("h-full first:rounded-l-full last:rounded-r-full", cfg.bg)}
              style={{ width: `${pct}%` }}
              title={`${cfg.label}: ${counts[s]}`}
            />
          )
        })}
      </div>

      {/* State legend */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {STATE_ORDER.filter((s) => counts[s] > 0).map((s) => {
          const cfg = STATE_CONFIG[s]
          return (
            <span key={s} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={cn("inline-block h-2 w-2 rounded-full", cfg.bg)} />
              {cfg.label}
            </span>
          )
        })}
      </div>

      <p className="mt-3 text-[10px] text-muted-foreground/60">
        {version}
      </p>
    </div>
  )
}
