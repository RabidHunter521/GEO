"use client"

import { useState, useEffect, useTransition } from "react"
import { Loader2, RefreshCw, FileText, Trophy, Sparkles, Copy } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import {
  generateRoadmapAction,
  refreshRoadmapAction,
  generateRoadmapItemContentAction,
} from "./actions"
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

function RoadmapItemCard({
  clientId,
  roadmapId,
  index,
  item,
  onUpdated,
}: {
  clientId: string
  roadmapId: string
  index: number
  item: RoadmapItem
  onUpdated: (roadmap: ContentRoadmap) => void
}) {
  const [open, setOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasArticle = !!item.article_content

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    try {
      const updated = await generateRoadmapItemContentAction(clientId, roadmapId, index)
      onUpdated(updated)
    } catch {
      setError("Couldn't write this article. Please try again.")
    } finally {
      setGenerating(false)
    }
  }

  async function handleCopy() {
    if (!item.article_content) return
    await navigator.clipboard.writeText(item.article_content)
    toast.success("Article copied to clipboard")
  }

  return (
    <>
      <div className="rounded-lg border bg-card p-4 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className="font-semibold">
            Week {item.week}
          </Badge>
          <Badge variant="outline" className={PRIORITY_STYLE[item.priority] ?? PRIORITY_STYLE.low}>
            {item.priority}
          </Badge>
          <Badge variant="outline" className="gap-1 text-muted-foreground">
            <FileText className="h-3 w-3" />
            {item.content_type}
          </Badge>
        </div>

        <button
          type="button"
          onClick={() => setOpen(true)}
          className="block text-left text-sm font-medium leading-snug text-foreground hover:text-primary hover:underline"
        >
          {item.suggested_title}
        </button>

        <p className="text-xs text-muted-foreground">{item.theme}</p>
        {item.rationale && (
          <p className="text-xs text-muted-foreground leading-relaxed">{item.rationale}</p>
        )}
        {item.competitors_winning.length > 0 && (
          <p className="text-xs text-score-low">
            Your competitors are winning here: {item.competitors_winning.join(", ")}
          </p>
        )}

        <div className="pt-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setOpen(true)}
          >
            <FileText className="h-3.5 w-3.5 mr-1.5" />
            {hasArticle ? "Read article" : "Write article"}
          </Button>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{item.suggested_title}</DialogTitle>
            <DialogDescription>
              Week {item.week} · {item.content_type} · {item.theme}
            </DialogDescription>
          </DialogHeader>

          {hasArticle ? (
            <div className="space-y-3">
              <div className="flex justify-end">
                <Button type="button" variant="outline" size="sm" onClick={handleCopy}>
                  <Copy className="h-3.5 w-3.5 mr-1.5" />
                  Copy
                </Button>
              </div>
              <article className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                {item.article_content}
              </article>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <Sparkles className="mx-auto mb-3 h-6 w-6 text-primary" />
              <p className="text-sm font-medium">No draft written yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Generate a full, publish-ready article draft for this piece with Claude.
              </p>
              {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
              <Button type="button" className="mt-4" onClick={handleGenerate} disabled={generating}>
                {generating ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4 mr-2" />
                )}
                {generating ? "Writing…" : "Write the article"}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

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

  const showResults = roadmap && roadmap.status === "completed"
  const isEmptyResult = showResults && roadmap.roadmap_json.length === 0

  // Keep each item's original index (needed to address it for article generation)
  // while presenting the plan ordered week 1 → 12.
  const orderedItems = (roadmap?.roadmap_json ?? [])
    .map((item, index) => ({ item, index }))
    .sort((a, b) => a.item.week - b.item.week)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Content Roadmap
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            A prioritized 90-day plan of 12 weekly content pieces, built from the questions where
            your competitors are winning. Click any title to read or generate the full article.
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
            Click &ldquo;Generate plan&rdquo; to turn this client&apos;s lost queries into a 12-week
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

      {showResults && !isEmptyResult && roadmap && (
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

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {orderedItems.map(({ item, index }) => (
              <RoadmapItemCard
                key={index}
                clientId={clientId}
                roadmapId={roadmap.id}
                index={index}
                item={item}
                onUpdated={setRoadmap}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
