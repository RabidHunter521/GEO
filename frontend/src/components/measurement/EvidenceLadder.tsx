import { cn } from "@/lib/utils"
import type { ImpactSummary, ImpactSummaryPublic } from "@/types"

const CURRENCY_SYMBOLS: Record<string, string> = {
  MYR: "RM",
  USD: "$",
  EUR: "€",
  GBP: "£",
  SGD: "S$",
  AUD: "A$",
}

const EVIDENCE_LEVELS = [
  { key: "observed",   label: "Directly measured",       field: "observed_value_minor" },
  { key: "attributed", label: "Rule-based attribution",  field: "attributed_value_minor" },
  { key: "assisted",   label: "AI-assisted matching",    field: "assisted_value_minor" },
  { key: "estimated",  label: "Modeled projection",      field: "estimated_value_minor" },
] as const

function formatCurrency(minorUnits: number, symbol: string): string {
  const major = minorUnits / 100
  return `${symbol}${major.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function EvidenceLadder({
  summary,
}: {
  summary: ImpactSummary | ImpactSummaryPublic
}) {
  const symbol = CURRENCY_SYMBOLS[summary.currency] ?? summary.currency + " "
  const hasAnyValue = EVIDENCE_LEVELS.some(
    (l) => (summary[l.field as keyof typeof summary] as number) > 0
  )

  if (!hasAnyValue) {
    return (
      <div className="rounded-xl border bg-card p-5">
        <p className="text-sm text-muted-foreground">
          No conversion evidence recorded yet
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {EVIDENCE_LEVELS.map((level) => {
        const value = summary[level.field as keyof typeof summary] as number
        const isEstimated = level.key === "estimated"
        const eventCount = summary.event_count_by_level?.[level.key] ?? 0

        if (value === 0 && eventCount === 0) return null

        return (
          <div
            key={level.key}
            className={cn(
              "flex items-center justify-between gap-4 rounded-lg border p-3",
              isEstimated
                ? "border-dashed border-muted-foreground/30"
                : "border-border",
            )}
          >
            <div className="min-w-0">
              <p
                className={cn(
                  "text-sm font-medium",
                  isEstimated ? "italic text-muted-foreground" : "text-foreground",
                )}
              >
                {level.label}
                {isEstimated && (
                  <span className="ml-1.5 text-xs text-muted-foreground">(estimated)</span>
                )}
              </p>
              {eventCount > 0 && (
                <p className="text-xs text-muted-foreground">
                  {eventCount} {eventCount === 1 ? "event" : "events"}
                </p>
              )}
            </div>
            <p
              className={cn(
                "shrink-0 font-display text-lg font-semibold tabular-nums",
                isEstimated ? "italic text-muted-foreground" : "text-foreground",
              )}
            >
              {formatCurrency(value, symbol)}
            </p>
          </div>
        )
      })}

      {/* Caveats */}
      {summary.caveats && summary.caveats.length > 0 && (
        <div className="mt-1 space-y-0.5">
          {summary.caveats.map((caveat, i) => (
            <p key={i} className="text-[10px] leading-relaxed text-muted-foreground/60">
              {caveat}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
