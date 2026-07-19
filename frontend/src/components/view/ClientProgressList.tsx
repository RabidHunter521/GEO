// frontend/src/components/view/ClientProgressList.tsx
// Read-only "What We're Fixing" loop: tracked hallucinations and competitor-won
// queries with their Flagged -> In progress -> Corrected status. Proof of the
// work behind the retainer. No mutations — status is set on the admin side.
//
// The backend emits one item per platform per query, so the same question
// ("Where can I find X in KL?") can appear up to 4x. Grouped here by query so
// the client sees one row with platform chips instead of a wall of near-
// identical red "Flagged" rows — that read as "nothing is being handled" even
// when 1 of 4 platforms had already been fixed.
import { CheckCircle2, Loader2, AlertTriangle } from "lucide-react"
import type { ClientViewProgressItem } from "@/types"
import { cn } from "@/lib/utils"

type Status = ClientViewProgressItem["status"]

const STATUS_STYLE: Record<Status, { chip: string; icon: typeof CheckCircle2; label: string }> = {
  flagged: {
    chip: "bg-score-low-bg text-score-low border-score-low/25",
    icon: AlertTriangle,
    label: "Flagged",
  },
  in_progress: {
    chip: "bg-score-watch-bg text-score-watch border-score-watch/30",
    icon: Loader2,
    label: "In progress",
  },
  corrected: {
    chip: "bg-score-strong-bg text-score-strong border-score-strong/25",
    icon: CheckCircle2,
    label: "Fixed",
  },
}

const STATUS_RANK: Record<Status, number> = { flagged: 0, in_progress: 1, corrected: 2 }
const MAX_VISIBLE = 6

interface ProgressGroup {
  key: string
  label: string
  type_label: string
  detail: string | null
  platforms: string[]
  status: Status
  correctedCount: number
  total: number
}

function groupByQuery(items: ClientViewProgressItem[]): ProgressGroup[] {
  const byKey = new Map<
    string,
    { label: string; type_label: string; detail: string | null; platforms: string[]; statuses: Status[] }
  >()
  for (const item of items) {
    const key = `${item.item_type}:${item.label}`
    const g = byKey.get(key)
    if (!g) {
      byKey.set(key, {
        label: item.label,
        type_label: item.type_label,
        detail: item.detail,
        platforms: item.platform_label ? [item.platform_label] : [],
        statuses: [item.status],
      })
      continue
    }
    if (item.platform_label && !g.platforms.includes(item.platform_label)) {
      g.platforms.push(item.platform_label)
    }
    g.detail = g.detail ?? item.detail
    g.statuses.push(item.status)
  }

  const groups: ProgressGroup[] = [...byKey.entries()].map(([key, g]) => {
    const correctedCount = g.statuses.filter((s) => s === "corrected").length
    const status: Status =
      correctedCount === g.statuses.length
        ? "corrected"
        : correctedCount > 0 || g.statuses.some((s) => s === "in_progress")
          ? "in_progress"
          : "flagged"
    return {
      key,
      label: g.label,
      type_label: g.type_label,
      detail: g.detail,
      platforms: g.platforms,
      status,
      correctedCount,
      total: g.statuses.length,
    }
  })

  // Stable sort: flagged/in-progress first (client's attention), fixed last —
  // mirroring the backend's own item ordering within each bucket.
  return groups.sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status])
}

export function ClientProgressList({ items }: { items: ClientViewProgressItem[] }) {
  if (items.length === 0) return null

  const groups = groupByQuery(items)
  const fixedCount = groups.filter((g) => g.status === "corrected").length
  const visible = groups.slice(0, MAX_VISIBLE)
  const hiddenCount = groups.length - visible.length

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          What We&apos;re Fixing
        </h2>
        {fixedCount > 0 && (
          <span className="rounded-full bg-score-strong-bg px-2.5 py-0.5 text-xs font-medium text-score-strong">
            {fixedCount} fixed
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Issues your SeenBy team is tracking and working through — from flagged to
        fixed.
      </p>

      <ul className="mt-4 space-y-2">
        {visible.map((group) => {
          const style = STATUS_STYLE[group.status]
          const Icon = style.icon
          return (
            <li
              key={group.key}
              className="flex items-start justify-between gap-3 rounded-md border bg-background p-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium leading-snug">
                  &ldquo;{group.label}&rdquo;
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {group.type_label}
                  {group.platforms.length > 0 ? ` · ${group.platforms.join(", ")}` : ""}
                  {group.detail ? ` · AI recommends ${group.detail}` : ""}
                </p>
              </div>
              <span
                className={cn(
                  "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                  style.chip,
                )}
              >
                <Icon className="h-3 w-3" />
                {group.total > 1 ? `${style.label} · ${group.correctedCount}/${group.total}` : style.label}
              </span>
            </li>
          )
        })}
      </ul>
      {hiddenCount > 0 && (
        <p className="mt-3 text-center text-xs text-muted-foreground">
          +{hiddenCount} more {hiddenCount === 1 ? "question" : "questions"} being tracked
        </p>
      )}
    </div>
  )
}
