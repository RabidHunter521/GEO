"use client"

import { useState, useEffect, useTransition } from "react"
import { Loader2, RefreshCw, FileText, Trophy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { generateRoadmapAction, refreshRoadmapAction } from "./actions"
import type { ContentRoadmap, RoadmapItem } from "@/types"

interface Props {
  clientId: string
  initialRoadmap: ContentRoadmap | null
}

const PRIORITY_STYLE: Record<string, string> = {
  high: "border-score-low/30 bg-score-low-bg text-score-low",
  medium: "border-score-watch/30 bg-score-watch-bg text-score-watch",
  low: "border-muted-foreground/30 text-muted-foreground",
}

const MONTHS = [1, 2, 3] as const
const MONTH_LABEL: Record<number, string> = { 1: "Month 1", 2: "Month 2", 3: "Month 3" }

export function ContentRoadmapClient({ clientId, initialRoadmap }: Props) {
  const [roadmap, setRoadmap] = useState<ContentRoadmap | null>(initialRoadmap)
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  const isRunning = roadmap?.status === "pending" || roadmap?.status === "running"

  useEffect(() => {
    if (!isRunning) return
    const interval = setInterval(async () => {
      const updated = await refreshRoadmapAction(clientId)
      if (updated) setRoadmap(updated)
    }, 3000)
    return () => clearInterval(interval)
  }, [isRunning, clientId])

  function handleRun() {
    startTransition(async () => {
      setError(null)
      try {
        const result = await generateRoadmapAction(clientId)
        setRoadmap(result)
      } catch {
        setError("Roadmap generation failed. Please try again.")
      }
    })
  }

  function itemsForMonth(month: number): RoadmapItem[] {
    return (roadmap?.roadmap_json ?? []).filter((i) => i.month === month)
  }

  const showResults = roadmap && roadmap.status === "completed"
  const isEmptyResult = showResults && roadmap.roadmap_json.length === 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Content Roadmap
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            A prioritized 90-day content plan built from the questions where your competitors are
            winning — the queries AI assistants don&apos;t yet associate with this brand.
          </p>
        </div>
        <Button onClick={handleRun} disabled={isPending || isRunning} className="shrink-0">
          {isPending || isRunning ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          {roadmap ? "Re-generate plan" : "Generate plan"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {roadmap?.status === "failed" && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          The last generation failed. Click &ldquo;Re-generate plan&rdquo; to try again.
        </div>
      )}

      {/* Empty state — never generated */}
      {!roadmap && !isPending && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">No roadmap yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Generate plan&rdquo; to turn this client&apos;s lost queries into a 90-day
            content plan. Run a scan first so there&apos;s competitor data to work from.
          </p>
        </div>
      )}

      {/* Running state */}
      {(isPending || isRunning) && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3" />
          <p className="text-sm font-medium">Building the roadmap with Claude&hellip;</p>
          <p className="text-xs mt-1">This usually takes 10&ndash;30 seconds.</p>
        </div>
      )}

      {/* Completed but nothing to plan — client already seen everywhere */}
      {isEmptyResult && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <Trophy className="h-6 w-6 mx-auto mb-3 text-score-strong" />
          <p className="text-sm font-medium">You&apos;re already seen across tracked queries</p>
          <p className="text-xs mt-1">
            No competitor is winning queries this brand is missing — there&apos;s nothing to plan
            right now. Re-generate after the next scan.
          </p>
        </div>
      )}

      {showResults && !isEmptyResult && (
        <>
          <p className="text-xs text-muted-foreground">
            Generated{" "}
            {new Date(roadmap.generated_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            })}{" "}
            · from {roadmap.source_query_count} lost quer
            {roadmap.source_query_count === 1 ? "y" : "ies"}
          </p>

          <div className="grid gap-4 md:grid-cols-3">
            {MONTHS.map((month) => {
              const items = itemsForMonth(month)
              return (
                <div key={month} className="rounded-lg border p-4 space-y-3">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-sm font-semibold">{MONTH_LABEL[month]}</h3>
                    <span className="text-sm font-medium text-muted-foreground">
                      {items.length}
                    </span>
                  </div>
                  {items.length === 0 ? (
                    <p className="text-xs text-muted-foreground/60">Nothing planned.</p>
                  ) : (
                    items.map((item, i) => (
                      <div key={`${item.suggested_title}-${i}`} className="rounded-md border bg-muted/10 p-3 space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant="outline" className={PRIORITY_STYLE[item.priority] ?? PRIORITY_STYLE.low}>
                            {item.priority}
                          </Badge>
                          <Badge variant="outline" className="gap-1 text-muted-foreground">
                            <FileText className="h-3 w-3" />
                            {item.content_type}
                          </Badge>
                        </div>
                        <p className="text-sm font-medium leading-snug">{item.suggested_title}</p>
                        <p className="text-xs text-muted-foreground">{item.theme}</p>
                        {item.rationale && (
                          <p className="text-xs text-muted-foreground leading-relaxed">{item.rationale}</p>
                        )}
                        {item.competitors_winning.length > 0 && (
                          <p className="text-xs text-score-low">
                            Your competitors are winning here: {item.competitors_winning.join(", ")}
                          </p>
                        )}
                        {item.target_queries.length > 0 && (
                          <ul className="space-y-0.5">
                            {item.target_queries.map((q) => (
                              <li key={q} className="text-xs text-muted-foreground">
                                &ldquo;{q}&rdquo;
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
