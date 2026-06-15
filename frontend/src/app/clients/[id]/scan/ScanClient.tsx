"use client"

import { useState, useEffect, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, Play, CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import type { Platform, Scan, ScanQueryResult } from "@/types"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"
import { triggerScanAction, flagHallucinationAction, refreshScanAction } from "./actions"

interface Props {
  clientId: string
  clientName: string
  initialScan: Scan | null
}

const CATEGORY_LABELS: Record<string, string> = {
  brand: "Brand",
  comparison: "Comparison",
  recommendation: "Recommendation",
  local: "Local",
}

export function ScanClient({ clientId, clientName, initialScan }: Props) {
  const [scan, setScan] = useState<Scan | null>(initialScan)
  const [isPending, startTransition] = useTransition()
  const [flaggingId, setFlaggingId] = useState<string | null>(null)
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(
    () => new Set(initialScan?.results.filter((r) => r.hallucination_flagged).map((r) => r.id) ?? [])
  )
  const [platformFilter, setPlatformFilter] = useState<Platform | "all">("all")

  const isActive = scan?.status === "running" || scan?.status === "pending"

  useEffect(() => {
    setFlaggedIds(
      new Set(scan?.results.filter((r) => r.hallucination_flagged).map((r) => r.id) ?? [])
    )
  }, [scan?.id, scan?.results])

  useEffect(() => {
    if (!isActive) return
    const interval = setInterval(async () => {
      const updated = await refreshScanAction(clientId)
      if (updated) setScan(updated)
    }, 3000)
    return () => clearInterval(interval)
  }, [isActive, clientId])

  function handleTrigger() {
    startTransition(async () => {
      const newScan = await triggerScanAction(clientId)
      if (newScan) setScan(newScan)
    })
  }

  function handleFlag(resultId: string) {
    if (!scan) return
    setFlaggingId(resultId)
    startTransition(async () => {
      await flagHallucinationAction(scan.id, resultId, clientId)
      setFlaggingId(null)
      setFlaggedIds((prev) => {
        const updated = new Set(prev)
        updated.add(resultId)
        return updated
      })
    })
  }

  const allClientResults = scan?.results.filter((r) => r.competitor_id === null) ?? []
  const scannedPlatforms = SCAN_PLATFORMS.filter((p) =>
    allClientResults.some((r) => r.platform === p),
  )
  const matchesFilter = (r: ScanQueryResult) =>
    platformFilter === "all" || r.platform === platformFilter
  const clientResults = allClientResults.filter(matchesFilter)
  const competitorGroups = groupByCompetitor(
    scan?.results.filter((r) => r.competitor_id !== null && matchesFilter(r)) ?? [],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Scan &amp; Visibility
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            How AI models respond to queries about {clientName}.
          </p>
        </div>
        <Button size="sm" onClick={handleTrigger} disabled={isPending || isActive}>
          {isActive ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Play className="h-4 w-4 mr-2" />
          )}
          {isActive ? "Scan running…" : "Run New Scan"}
        </Button>
      </div>

      {!scan && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">No scans yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Run New Scan&rdquo; to trigger the first scan.
          </p>
        </div>
      )}

      {scan?.status === "failed" && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          The last scan failed. Trigger a new scan to retry.
        </div>
      )}

      {isActive && (
        <div className="rounded-lg border bg-muted/30 p-8 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm font-medium">Scan in progress</p>
          <p className="text-sm text-muted-foreground mt-1">
            Querying ChatGPT, Perplexity, Gemini and Claude across 8 topics each.
            This can take a few minutes.
          </p>
        </div>
      )}

      {scan?.status === "completed" && (
        <div className="space-y-6">
          <p className="text-xs text-muted-foreground">
            Completed {formatDate(scan.completed_at!)} &middot;{" "}
            {scannedPlatforms.length > 0
              ? `Platforms: ${scannedPlatforms.map((p) => PLATFORM_LABELS[p]).join(", ")}`
              : `Platform: ${scan.platform}`}
          </p>

          {/* Per-platform visibility summary */}
          {scannedPlatforms.length > 1 && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {scannedPlatforms.map((p) => {
                const platformResults = allClientResults.filter((r) => r.platform === p)
                const seen = platformResults.filter((r) => r.brand_detected).length
                const pct = platformResults.length
                  ? Math.round((seen / platformResults.length) * 100)
                  : 0
                return (
                  <div key={p} className="rounded-lg border bg-card px-4 py-3">
                    <p className="text-xs font-medium text-muted-foreground">
                      {PLATFORM_LABELS[p]}
                    </p>
                    <p className="font-display text-xl font-bold tabular-nums mt-1">
                      {pct}%
                    </p>
                    <p className="text-xs text-muted-foreground">
                      visibility frequency &middot; {seen}/{platformResults.length} queries
                    </p>
                  </div>
                )
              })}
            </div>
          )}

          {/* Platform filter */}
          {scannedPlatforms.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              {(["all", ...scannedPlatforms] as const).map((p) => (
                <Button
                  key={p}
                  variant={platformFilter === p ? "default" : "outline"}
                  size="sm"
                  className="h-7 px-3 text-xs"
                  onClick={() => setPlatformFilter(p)}
                >
                  {p === "all" ? "All platforms" : PLATFORM_LABELS[p]}
                </Button>
              ))}
            </div>
          )}

          {/* Summary stats */}
          {clientResults.length > 0 && (() => {
            const seen = clientResults.filter((r) => r.brand_detected).length
            const pct = Math.round((seen / clientResults.length) * 100)
            const ranked = clientResults
              .map((r) => r.recommendation_position)
              .filter((p): p is number => p != null)
            const avgRank =
              ranked.length > 0
                ? (ranked.reduce((a, b) => a + b, 0) / ranked.length).toFixed(1)
                : null
            return (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
                  <span className="font-display text-2xl font-bold tabular-nums text-primary">
                    {seen}/{clientResults.length}
                  </span>
                  <div>
                    <p className="text-sm font-medium leading-tight">queries — your brand was seen by AI</p>
                    <p className="text-xs text-muted-foreground">
                      visibility frequency: <span className="font-semibold">{pct}%</span>
                    </p>
                  </div>
                </div>
                {avgRank && (
                  <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
                    <span className="font-display text-2xl font-bold tabular-nums text-primary">
                      #{avgRank}
                    </span>
                    <div>
                      <p className="text-sm font-medium leading-tight">average AI Search Ranking</p>
                      <p className="text-xs text-muted-foreground">
                        across {ranked.length} ranked {ranked.length === 1 ? "answer" : "answers"}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )
          })()}

          <section>
            <h3 className="text-sm font-semibold mb-3">
              Your Brand — {clientResults.length} queries
            </h3>
            <ResultsTable
              results={clientResults}
              flaggingId={flaggingId}
              flaggedIds={flaggedIds}
              onFlag={handleFlag}
            />
          </section>

          {competitorGroups.map(({ competitorName, results }) => (
            <section key={competitorName}>
              <h3 className="text-sm font-semibold mb-3">
                Competitor: {competitorName} — {results.length} queries
              </h3>
              <ResultsTable
                results={results}
                flaggingId={flaggingId}
                flaggedIds={flaggedIds}
                onFlag={handleFlag}
              />
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function ResultsTable({
  results,
  flaggingId,
  flaggedIds,
  onFlag,
}: {
  results: ScanQueryResult[]
  flaggingId: string | null
  flaggedIds: Set<string>
  onFlag: (id: string) => void
}) {
  return (
    <div className="rounded-lg border overflow-hidden bg-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40">
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground w-28">
              Platform
            </th>
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground w-28">
              Category
            </th>
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">
              Query
            </th>
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground w-40">
              Status
            </th>
            <th className="px-4 py-2.5 text-right text-xs font-medium text-muted-foreground w-24">
              Flag
            </th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, i) => (
            <tr
              key={r.id}
              className={`${i < results.length - 1 ? "border-b" : ""} hover:bg-muted/20 transition-colors`}
            >
              <td className="px-4 py-3">
                <span className="text-xs font-medium">
                  {PLATFORM_LABELS[r.platform] ?? r.platform}
                </span>
              </td>
              <td className="px-4 py-3">
                <Badge variant="outline" className="text-xs font-normal">
                  {CATEGORY_LABELS[r.category] ?? r.category}
                </Badge>
              </td>
              <td className="px-4 py-3 text-muted-foreground text-sm">{r.query_text}</td>
              <td className="px-4 py-3">
                <div className="flex flex-col gap-1">
                  {r.brand_detected ? (
                    <span className="flex items-center gap-1.5 text-score-strong text-sm font-medium">
                      <CheckCircle className="h-3.5 w-3.5 shrink-0" />
                      Seen by AI
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-muted-foreground text-sm">
                      <XCircle className="h-3.5 w-3.5 shrink-0" />
                      Not seen by AI
                    </span>
                  )}
                  {r.recommendation_position != null && (
                    <Badge
                      variant="outline"
                      className="w-fit gap-1 border-primary/30 bg-primary/5 text-primary text-xs font-normal"
                    >
                      AI Search Ranking #{r.recommendation_position}
                    </Badge>
                  )}
                </div>
              </td>
              <td className="px-4 py-3 text-right">
                {flaggedIds.has(r.id) ? (
                  <span className="text-xs text-muted-foreground">Flagged</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-score-watch hover:text-score-watch hover:bg-score-watch-bg"
                    onClick={() => onFlag(r.id)}
                    disabled={flaggingId === r.id}
                  >
                    {flaggingId === r.id ? (
                      <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    ) : (
                      <AlertTriangle className="h-3 w-3 mr-1" />
                    )}
                    Flag
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function groupByCompetitor(results: ScanQueryResult[]) {
  const groups = new Map<string, { competitorName: string; results: ScanQueryResult[] }>()
  for (const r of results) {
    const key = r.competitor_id!
    if (!groups.has(key)) {
      groups.set(key, { competitorName: r.competitor_name ?? key, results: [] })
    }
    groups.get(key)!.results.push(r)
  }
  return Array.from(groups.values())
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
