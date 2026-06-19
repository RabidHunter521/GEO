// frontend/src/components/view/ClientProgressList.tsx
// Read-only "What We're Fixing" loop: tracked hallucinations and competitor-won
// queries with their Flagged -> In progress -> Corrected status. Proof of the
// work behind the retainer. No mutations — status is set on the admin side.
import { CheckCircle2, Loader2, AlertTriangle } from "lucide-react"
import type { ClientViewProgressItem } from "@/types"
import { cn } from "@/lib/utils"

const STATUS_STYLE: Record<
  ClientViewProgressItem["status"],
  { chip: string; icon: typeof CheckCircle2 }
> = {
  flagged: {
    chip: "bg-score-low-bg text-score-low border-score-low/25",
    icon: AlertTriangle,
  },
  in_progress: {
    chip: "bg-score-watch-bg text-score-watch border-score-watch/30",
    icon: Loader2,
  },
  corrected: {
    chip: "bg-score-strong-bg text-score-strong border-score-strong/25",
    icon: CheckCircle2,
  },
}

export function ClientProgressList({ items }: { items: ClientViewProgressItem[] }) {
  if (items.length === 0) return null

  const correctedCount = items.filter((i) => i.status === "corrected").length

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          What We&apos;re Fixing
        </h2>
        {correctedCount > 0 && (
          <span className="rounded-full bg-score-strong-bg px-2.5 py-0.5 text-xs font-medium text-score-strong">
            {correctedCount} resolved
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Issues your SeenBy team is tracking and working through — from flagged to
        corrected.
      </p>

      <ul className="mt-4 space-y-2">
        {items.map((item, i) => {
          const style = STATUS_STYLE[item.status]
          const Icon = style.icon
          return (
            <li
              key={`${item.item_type}-${i}`}
              className="flex items-start justify-between gap-3 rounded-md border bg-background p-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium leading-snug">
                  &ldquo;{item.label}&rdquo;
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {item.type_label}
                  {item.platform_label ? ` · ${item.platform_label}` : ""}
                  {item.detail ? ` · AI recommends ${item.detail}` : ""}
                </p>
              </div>
              <span
                className={cn(
                  "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                  style.chip,
                )}
              >
                <Icon className="h-3 w-3" />
                {item.status_label}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
