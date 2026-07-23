"use client"

import { useState, useEffect, useTransition } from "react"
import Link from "next/link"
import { Loader2, RefreshCw, CheckCircle, XCircle, Lightbulb } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { runContentAnalysisAction, refreshContentGapsAction } from "./actions"
import type { ContentAnalysis, ContentTopic, SuggestedContentItem } from "@/types"

interface Props {
  clientId: string
  initialAnalysis: ContentAnalysis | null
}

const STATUS_STYLE = {
  strong: {
    label: "Strong topics",
    badge: "border-score-strong/30 bg-score-strong-bg text-score-strong",
    help: "Covered in depth — these are working for you.",
  },
  weak: {
    label: "Weak topics",
    badge: "border-score-watch/30 bg-score-watch-bg text-score-watch",
    help: "Mentioned only briefly — worth expanding.",
  },
  missing: {
    label: "Missing topics",
    badge: "border-score-low/30 bg-score-low-bg text-score-low",
    help: "Not covered yet — your biggest content opportunities.",
  },
} as const

type Status = keyof typeof STATUS_STYLE
const STATUS_ORDER: Status[] = ["missing", "weak", "strong"]

export function ContentGapsClient({ clientId, initialAnalysis }: Props) {
  const [analysis, setAnalysis] = useState<ContentAnalysis | null>(initialAnalysis)
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  const isRunning = analysis?.status === "pending" || analysis?.status === "running"

  useEffect(() => {
    if (!isRunning) return
    const interval = setInterval(async () => {
      const updated = await refreshContentGapsAction(clientId)
      if (updated) setAnalysis(updated)
    }, 3000)
    return () => clearInterval(interval)
  }, [isRunning, clientId])

  function handleRun() {
    startTransition(async () => {
      setError(null)
      try {
        const result = await runContentAnalysisAction(clientId)
        setAnalysis(result)
      } catch {
        setError("Analysis failed. Please try again.")
      }
    })
  }

  function topicsByStatus(status: Status): ContentTopic[] {
    return (analysis?.topics_json ?? []).filter((t) => t.status === status)
  }

  const suggestions = analysis?.suggested_content_json ?? []
  const entities = analysis?.entities_json ?? []
  const coveredCount = entities.filter((e) => e.covered).length
  const metrics = analysis?.content_metrics_json
  const showResults = analysis && analysis.status === "completed"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Content Gaps
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            See which industry topics and entities your website covers — and what to create next
            so AI search engines feature you more often.
          </p>
          <Link
            href={`/clients/${clientId}/content-studio`}
            className="mt-1 inline-block text-sm text-primary underline-offset-4 hover:underline"
          >
            Turn these into content &rarr;
          </Link>
        </div>
        <Button onClick={handleRun} disabled={isPending || isRunning} className="shrink-0">
          {isPending || isRunning ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          {analysis ? "Re-run analysis" : "Run analysis"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {analysis?.status === "failed" && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          The last analysis failed. Click &ldquo;Re-run analysis&rdquo; to try again.
        </div>
      )}

      {/* Empty state */}
      {!analysis && !isPending && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">No analysis yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Run analysis&rdquo; to crawl the website and map its topic coverage.
          </p>
        </div>
      )}

      {/* Running state */}
      {(isPending || isRunning) && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3" />
          <p className="text-sm font-medium">Crawling the website and analysing with Claude&hellip;</p>
          <p className="text-xs mt-1">This usually takes 20&ndash;40 seconds.</p>
        </div>
      )}

      {showResults && (
        <>
          <p className="text-xs text-muted-foreground">
            Last analysed{" "}
            {new Date(analysis.analyzed_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            })}{" "}
            · {analysis.pages_crawled} page{analysis.pages_crawled === 1 ? "" : "s"} crawled
          </p>

          {/* Topic columns */}
          <div className="grid gap-4 md:grid-cols-3">
            {STATUS_ORDER.map((status) => {
              const topics = topicsByStatus(status)
              const meta = STATUS_STYLE[status]
              return (
                <div key={status} className="rounded-lg border p-4">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-sm font-semibold">{meta.label}</h3>
                    <span className="text-sm font-medium text-muted-foreground">
                      {topics.length}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 mb-3">{meta.help}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {topics.length === 0 ? (
                      <span className="text-xs text-muted-foreground/60">None</span>
                    ) : (
                      topics.map((t) => (
                        <Badge
                          key={t.topic}
                          variant="outline"
                          className={meta.badge}
                        >
                          {t.topic}
                        </Badge>
                      ))
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Suggested content ideas */}
          {suggestions.length > 0 && (
            <div className="rounded-lg border p-5 space-y-4">
              <div>
                <h3 className="text-sm font-semibold">Suggested content ideas</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Content to create so AI search engines start featuring this brand on these
                  topics.
                </p>
              </div>
              <div className="space-y-3">
                {suggestions.map((s: SuggestedContentItem, i: number) => (
                  <div key={`${s.topic}-${i}`} className="rounded-md border bg-muted/10 px-4 py-3 flex gap-3">
                    <Lightbulb className="h-4 w-4 shrink-0 text-score-watch mt-0.5" />
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline" className="border-score-low/30 bg-score-low-bg text-score-low">
                          {s.topic}
                        </Badge>
                        <p className="text-sm font-medium">{s.title}</p>
                      </div>
                      <p className="text-sm text-muted-foreground leading-relaxed">{s.rationale}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Entity coverage */}
          <div className="rounded-lg border p-5 space-y-4">
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-semibold">Entity coverage</h3>
              <span className="text-sm text-muted-foreground">
                <span className="text-2xl font-semibold text-foreground">{coveredCount}</span>
                {" / "}
                {entities.length}
                {" · "}
                {analysis.entity_coverage_score.toFixed(0)}%
              </span>
            </div>
            <p className="text-xs text-muted-foreground -mt-2">
              The concepts and terms AI models associate with this industry. Covering the gaps
              helps AI systems recognise the brand.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {entities.map((e) => (
                <Badge
                  key={e.entity}
                  variant="outline"
                  className={
                    e.covered
                      ? "gap-1 border-score-strong/30 bg-score-strong-bg text-score-strong"
                      : "gap-1 text-muted-foreground"
                  }
                >
                  {e.covered ? (
                    <CheckCircle className="h-3 w-3" />
                  ) : (
                    <XCircle className="h-3 w-3" />
                  )}
                  {e.entity}
                </Badge>
              ))}
            </div>
          </div>

          {/* Content quality assist (Feature B) */}
          <div className="rounded-lg border p-5 space-y-4">
            <h3 className="text-sm font-semibold">Content quality signals</h3>
            {metrics && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Metric label="Words" value={metrics.word_count.toLocaleString()} />
                <Metric label="H1 headings" value={metrics.h1_count} />
                <Metric label="FAQ sections" value={metrics.faq_count} />
                <Metric label="Blog pages" value={metrics.blog_count} />
                <Metric
                  label="Structured data"
                  value={metrics.schema_present ? "Present" : "None"}
                />
              </div>
            )}
            {analysis.content_quality_recommendation && (
              <div className="rounded-md border bg-muted/10 px-4 py-3 flex gap-3">
                <Lightbulb className="h-4 w-4 shrink-0 text-score-watch mt-0.5" />
                <div>
                  <p className="text-sm font-medium">SeenBy content recommendation</p>
                  <p className="text-sm text-muted-foreground leading-relaxed mt-1">
                    {analysis.content_quality_recommendation}
                  </p>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border bg-muted/10 px-3 py-2.5">
      <p className="text-lg font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}
