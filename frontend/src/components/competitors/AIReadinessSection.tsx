// frontend/src/components/competitors/AIReadinessSection.tsx
"use client"

import { useState, useTransition } from "react"
import { CheckCircle, XCircle, Loader2, ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { CompetitorAIReadiness, SiteAIReadiness } from "@/types"
import { checkAIReadinessAction } from "@/app/clients/[id]/competitors/actions"

export function AIReadinessSection({ clientId }: { clientId: string }) {
  const [data, setData] = useState<CompetitorAIReadiness | null>(null)
  const [failed, setFailed] = useState(false)
  const [pending, startTransition] = useTransition()

  function handleCheck() {
    setFailed(false)
    startTransition(async () => {
      try {
        setData(await checkAIReadinessAction(clientId))
      } catch {
        setFailed(true)
      }
    })
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-lg font-semibold">AI Crawler Readiness</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Checks llms.txt, AI-bot access in robots.txt, and schema.org markup — for
            your site and each tracked competitor. Live check, not part of the score.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleCheck} disabled={pending} className="shrink-0">
          {pending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {pending ? "Checking…" : data ? "Re-check" : "Check AI Readiness"}
        </Button>
      </div>

      {failed && (
        <p className="mt-3 text-sm text-destructive">
          Couldn&apos;t complete the check — try again.
        </p>
      )}

      {data && (
        <div className="mt-4 divide-y">
          <AIReadinessRow site={data.client} isYou />
          {data.competitors.map((c) => (
            <AIReadinessRow key={c.name} site={c} />
          ))}
        </div>
      )}
    </div>
  )
}

function AIReadinessRow({ site, isYou = false }: { site: SiteAIReadiness; isYou?: boolean }) {
  if (!site.checked) {
    return (
      <div className="flex items-center justify-between py-3 text-sm">
        <span className="font-medium">
          {site.name}
          {isYou && <span className="text-muted-foreground"> (you)</span>}
        </span>
        <span className="text-xs text-muted-foreground">No website on file</span>
      </div>
    )
  }

  return (
    <div className="py-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {site.name}
          {isYou && <span className="text-muted-foreground"> (you)</span>}
        </span>
        <span className="text-xs text-muted-foreground">{site.website}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <span className="flex items-center gap-1.5 rounded-full border px-2.5 py-1">
          {site.has_llms_txt ? (
            <CheckCircle className="h-3.5 w-3.5 text-score-strong" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-muted-foreground/50" />
          )}
          llms.txt {site.has_llms_txt ? "found" : "missing"}
        </span>
        <span className="flex items-center gap-1.5 rounded-full border px-2.5 py-1">
          {site.schema_types.length > 0 ? (
            <CheckCircle className="h-3.5 w-3.5 text-score-strong" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-muted-foreground/50" />
          )}
          {site.schema_types.length > 0
            ? `Schema: ${site.schema_types.join(", ")}`
            : "No schema markup"}
        </span>
        {site.blocked_ai_bots.length > 0 && (
          <span className="flex items-center gap-1.5 rounded-full border border-score-watch/30 bg-score-watch-bg px-2.5 py-1 text-score-watch">
            <ShieldAlert className="h-3.5 w-3.5" />
            Blocks: {site.blocked_ai_bots.join(", ")}
          </span>
        )}
      </div>
    </div>
  )
}
