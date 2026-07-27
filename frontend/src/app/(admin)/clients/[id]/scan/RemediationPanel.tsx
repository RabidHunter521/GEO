// frontend/src/app/clients/[id]/scan/RemediationPanel.tsx
// Admin control for the remediation loop. Items are auto-created (flagged) and
// auto-corrected by scans; here the admin can mark one "In progress" or override
// status, and re-sync against the latest scan. The client sees the resulting
// Flagged → In progress → Corrected status on their shared view.
"use client"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Loader2, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import type { RemediationItem, RemediationStatus } from "@/types"
import { syncRemediationAction, setRemediationStatusAction } from "./actions"

const STATUSES: { value: RemediationStatus; label: string }[] = [
  { value: "flagged", label: "Flagged" },
  { value: "in_progress", label: "In progress" },
  { value: "corrected", label: "Corrected" },
]

const STATUS_CHIP: Record<RemediationStatus, string> = {
  flagged: "bg-score-low-bg text-score-low",
  in_progress: "bg-score-watch-bg text-score-watch",
  corrected: "bg-score-strong-bg text-score-strong",
}

const TYPE_LABEL: Record<RemediationItem["item_type"], string> = {
  hallucination: "Inaccurate AI answer",
  content_gap: "Competitor winning",
}

export function RemediationPanel({
  clientId,
  initialItems,
}: {
  clientId: string
  initialItems: RemediationItem[]
}) {
  const [items, setItems] = useState<RemediationItem[]>(initialItems)
  const [syncing, startSync] = useTransition()
  const [busyId, setBusyId] = useState<string | null>(null)

  function handleSync() {
    startSync(async () => {
      try {
        setItems(await syncRemediationAction(clientId))
      } catch {
        /* surfaced by the page on next load; keep the panel quiet */
      }
    })
  }

  async function handleStatus(itemId: string, status: RemediationStatus) {
    setBusyId(itemId)
    try {
      const updated = await setRemediationStatusAction(clientId, itemId, status)
      setItems((prev) => prev.map((i) => (i.id === itemId ? updated : i)))
    } catch {
      /* no-op */
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="space-y-4 rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">
            Remediation Progress
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Tracked hallucinations and competitor-won queries. The client sees these as
            Flagged → In progress → Corrected. Items auto-correct when the next scan no longer shows them.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={handleSync} disabled={syncing}>
          {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Sync to latest scan
        </Button>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No tracked items yet. Flag a hallucination above, or run a scan where a competitor wins a
          neutral query, then Sync.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex flex-col gap-2 rounded-md border bg-background p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium leading-snug">&ldquo;{item.label}&rdquo;</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {TYPE_LABEL[item.item_type]}
                  {item.platform ? ` · ${item.platform}` : ""}
                  {item.detail ? ` · ${item.detail}` : ""}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {STATUSES.map((s) => {
                  const active = item.status === s.value
                  return (
                    <button
                      key={s.value}
                      type="button"
                      disabled={busyId === item.id}
                      onClick={() => handleStatus(item.id, s.value)}
                      className={cn(
                        "rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors disabled:opacity-50",
                        active
                          ? STATUS_CHIP[s.value]
                          : "border text-muted-foreground hover:bg-muted/40",
                      )}
                    >
                      {s.label}
                    </button>
                  )
                })}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
