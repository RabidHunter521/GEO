"use client"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, Check, X } from "lucide-react"
import type { ActionRecommendation } from "@/types"
import { markActionDone, markActionDismissed } from "./actions"

const DIMENSION_LABELS: Record<ActionRecommendation["dimension"], string> = {
  ai_citability: "AI Citability",
  brand_authority: "Brand Authority",
  content_quality: "Content Quality",
  technical_foundations: "Technical Foundations",
  structured_data: "Structured Data",
}

interface Props {
  clientId: string
  initialActions: ActionRecommendation[]
}

export function ActionCenterCard({ clientId, initialActions }: Props) {
  const [actions, setActions] = useState(
    [...initialActions].sort((a, b) => b.estimated_impact - a.estimated_impact),
  )
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleResolve(actionId: string, status: "done" | "dismissed") {
    setPendingId(actionId)
    startTransition(async () => {
      if (status === "done") {
        await markActionDone(clientId, actionId)
      } else {
        await markActionDismissed(clientId, actionId)
      }
      setActions((prev) => prev.filter((a) => a.id !== actionId))
      setPendingId(null)
    })
  }

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Recommended Actions
      </h2>
      {actions.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          No actions yet — actions are generated automatically after each scan.
        </div>
      ) : (
        <div className="space-y-2">
          {actions.map((action) => (
            <div
              key={action.id}
              className="flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex-1">
                <p className="text-sm font-medium">{action.action_text}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="text-xs font-normal">
                    {DIMENSION_LABELS[action.dimension]}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    Estimated Impact: +{action.estimated_impact} GEO Score
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={() => handleResolve(action.id, "done")}
                  disabled={isPending && pendingId === action.id}
                >
                  {isPending && pendingId === action.id ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : (
                    <Check className="h-3 w-3 mr-1" />
                  )}
                  Mark done
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs text-muted-foreground"
                  onClick={() => handleResolve(action.id, "dismissed")}
                  disabled={isPending && pendingId === action.id}
                >
                  <X className="h-3 w-3 mr-1" />
                  Dismiss
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
