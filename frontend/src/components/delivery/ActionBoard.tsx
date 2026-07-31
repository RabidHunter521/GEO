"use client"

import { CalendarDays, UserRound } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { OUTCOME_ACTION_STATUS_LABELS, TERMINAL_OUTCOME_ACTION_STATUSES } from "@/lib/delivery-lifecycle"
import type { OutcomeAction, OutcomeActionStatus } from "@/types"

const columns: { title: string; statuses: OutcomeActionStatus[] }[] = [
  { title: "Recommended", statuses: ["detected", "recommended", "approved_internal"] },
  { title: "In progress", statuses: ["in_progress"] },
  { title: "Waiting for client", statuses: ["waiting_client"] },
  { title: "Ready to publish", statuses: ["ready_to_publish", "published"] },
  { title: "Verification", statuses: ["waiting_verification"] },
]

function displayDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-MY", { day: "numeric", month: "short" })
}

export function ActionBoard({
  actions,
  showCompleted,
  onShowCompletedChange,
  onSelect,
}: {
  actions: OutcomeAction[]
  showCompleted: boolean
  onShowCompletedChange: (value: boolean) => void
  onSelect: (action: OutcomeAction) => void
}) {
  const visibleColumns = showCompleted
    ? [{ title: "Completed", statuses: TERMINAL_OUTCOME_ACTION_STATUSES }]
    : columns

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{actions.length} actions</p>
        <Button size="sm" variant={showCompleted ? "secondary" : "outline"} onClick={() => onShowCompletedChange(!showCompleted)}>
          {showCompleted ? "Active actions" : "Completed"}
        </Button>
      </div>
      <div className={showCompleted ? "grid gap-4" : "grid gap-4 xl:grid-cols-5"}>
        {visibleColumns.map((column) => {
          const items = actions.filter((action) => column.statuses.includes(action.status))
          return (
            <section key={column.title} className="min-w-0">
              <div className="mb-2 flex items-center justify-between border-b pb-2">
                <h2 className="text-sm font-semibold">{column.title}</h2>
                <Badge variant="secondary">{items.length}</Badge>
              </div>
              <div className="space-y-2">
                {items.map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    onClick={() => onSelect(action)}
                    className="block w-full rounded-md border bg-card p-3 text-left transition-colors hover:border-primary/30 hover:bg-muted/30"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium leading-5">{action.title}</p>
                      <Badge variant="outline" className="shrink-0">{action.priority}</Badge>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {action.client_safe_summary ?? "No reviewed summary available."}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      {action.owner && <span className="inline-flex items-center gap-1"><UserRound className="h-3 w-3" />{action.owner}</span>}
                      {action.due_date && <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" />{displayDate(action.due_date)}</span>}
                    </div>
                    <p className="mt-2 text-xs font-medium text-muted-foreground">{OUTCOME_ACTION_STATUS_LABELS[action.status]}</p>
                  </button>
                ))}
                {items.length === 0 && <p className="rounded-md border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">No actions</p>}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
