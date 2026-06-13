// frontend/src/components/clients/NeedsAttentionQueue.tsx
// Compact queue of clients that need the admin's eyes: score drops, low
// scores, failed scans, stale or missing scans. Hidden when everyone is fine.
"use client"

import Link from "next/link"
import { AlertTriangle, ArrowDown, ArrowUp } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import {
  ATTENTION_LABELS,
  attentionReasons,
  scoreDelta,
  type AttentionReason,
} from "@/lib/client-list-utils"
import { cn } from "@/lib/utils"
import type { ClientListItem } from "@/types"

interface Props {
  clients: ClientListItem[]
  now: Date
}

function reasonLabel(reason: AttentionReason, client: ClientListItem): string {
  if (reason === "score_drop") {
    const delta = scoreDelta(client)
    return delta !== null ? `Score dropped ${Math.abs(Math.round(delta))} pts` : ATTENTION_LABELS.score_drop
  }
  return ATTENTION_LABELS[reason]
}

export function NeedsAttentionQueue({ clients, now }: Props) {
  const entries = clients
    .map((client) => ({ client, reasons: attentionReasons(client, now) }))
    .filter((e) => e.reasons.length > 0)

  if (entries.length === 0) return null

  return (
    <Card className="mb-6 border-amber-500/30">
      <CardHeader className="pb-2">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          Needs attention
          <span className="text-xs font-normal text-muted-foreground">
            {entries.length} client{entries.length !== 1 ? "s" : ""}
          </span>
        </p>
      </CardHeader>
      <CardContent className="divide-y p-0">
        {entries.map(({ client, reasons }) => {
          const delta = scoreDelta(client)
          const rounded = delta !== null ? Math.round(delta) : null
          return (
            <Link
              key={client.id}
              href={`/clients/${client.id}`}
              className="flex items-center justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-muted/50"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="min-w-0 truncate text-sm font-medium">{client.name}</span>
                <span className="flex shrink-0 items-center gap-1">
                  <ScoreBadge score={client.latest_overall_score} />
                  {rounded !== null && rounded !== 0 && (
                    <span
                      className={cn(
                        "flex items-center text-xs font-medium tabular-nums",
                        rounded > 0 ? "text-emerald-600" : "text-red-600",
                      )}
                    >
                      {rounded > 0 ? (
                        <ArrowUp className="h-3 w-3" />
                      ) : (
                        <ArrowDown className="h-3 w-3" />
                      )}
                      {Math.abs(rounded)}
                    </span>
                  )}
                </span>
              </div>
              <span className="flex shrink-0 flex-wrap justify-end gap-1">
                {reasons.map((reason) => (
                  <Badge
                    key={reason}
                    variant="outline"
                    className="border-amber-500/40 bg-amber-500/5 text-xs font-normal text-amber-700"
                  >
                    {reasonLabel(reason, client)}
                  </Badge>
                ))}
              </span>
            </Link>
          )
        })}
      </CardContent>
    </Card>
  )
}
