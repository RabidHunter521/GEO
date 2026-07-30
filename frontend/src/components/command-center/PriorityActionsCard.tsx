// frontend/src/components/command-center/PriorityActionsCard.tsx
// Existing open ActionRecommendation rows, highest estimated impact first
// (already ordered + capped server-side). CommandCenterAction carries no
// structured `dimension` field — command_center_service.py's `_action_reason`
// prefixes `reason` with the dimension label instead (e.g. "AI Citability:
// estimated +2.0 points to Growth Readiness"). We read that same label back
// out to link each row to the page where an admin actually resolves that
// dimension — the same href mapping the 5-dimension breakdown below this
// component uses (frontend/src/app/(admin)/clients/[id]/page.tsx DIMENSIONS).
import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { CommandCenterAction } from "@/types"

interface Props {
  actions: CommandCenterAction[]
  clientId: string
}

const DIMENSION_HREF: Record<string, string> = {
  "AI Citability": "scan",
  "Brand Authority": "settings#brand-authority",
  "Content Quality": "settings#content-quality",
  "Technical Foundations": "toolkit",
  "Structured Data": "toolkit",
}

const PRIORITY_CLASS: Record<CommandCenterAction["priority"], string> = {
  high: "bg-score-low-bg text-score-low border-score-low/25",
  medium: "bg-score-watch-bg text-score-watch border-score-watch/30",
  low: "bg-muted text-muted-foreground",
}

function dimensionHref(clientId: string, reason: string): string {
  const label = reason.split(":")[0]
  const suffix = DIMENSION_HREF[label] ?? "scan"
  return `/clients/${clientId}/${suffix}`
}

export function PriorityActionsCard({ actions, clientId }: Props) {
  return (
    <div className="rounded-lg border bg-card p-5">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
        Priority Actions
      </h2>
      {actions.length === 0 ? (
        <p className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
          No open actions — actions are generated automatically after each scan.
        </p>
      ) : (
        <div className="space-y-2">
          {actions.map((action) => (
            <Link
              key={action.id}
              href={dimensionHref(clientId, action.reason)}
              className="block rounded-md border p-3 transition-colors hover:border-primary/25 hover:bg-muted/30"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium">{action.action_text}</p>
                <Badge
                  variant="outline"
                  className={cn("shrink-0 text-[10px] font-semibold uppercase", PRIORITY_CLASS[action.priority])}
                >
                  {action.priority}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground/80">{action.reason}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
