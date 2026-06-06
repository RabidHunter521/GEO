"use client"

import { useState, useEffect, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, Play, CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import type { Scan, ScanQueryResult } from "@/types"
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
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(new Set())

  const isActive = scan?.status === "running" || scan?.status === "pending"

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

  const clientResults = scan?.results.filter((r) => r.competitor_id === null) ?? []
  const competitorGroups = groupByCompetitor(
    scan?.results.filter((r) => r.competitor_id !== null) ?? [],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Scan &amp; Visibility</h2>
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
            Querying Gemini across {clientResults.length > 0 ? clientResults.length : "8"} topics.
            This takes about 30 seconds.
          </p>
        </div>
      )}

      {scan?.status === "completed" && (
        <div className="space-y-6">
          <p className="text-xs text-muted-foreground">
            Completed {formatDate(scan.completed_at!)} &middot; Platform:{" "}
            {scan.platform}
          </p>

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
    <div className="rounded-lg border overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/30">
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
                <Badge variant="outline" className="text-xs font-normal">
                  {CATEGORY_LABELS[r.category] ?? r.category}
                </Badge>
              </td>
              <td className="px-4 py-3 text-muted-foreground text-sm">{r.query_text}</td>
              <td className="px-4 py-3">
                {r.brand_detected ? (
                  <span className="flex items-center gap-1.5 text-green-600 text-sm">
                    <CheckCircle className="h-3.5 w-3.5 shrink-0" />
                    Seen by AI
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-muted-foreground text-sm">
                    <XCircle className="h-3.5 w-3.5 shrink-0" />
                    Not yet seen by AI
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right">
                {flaggedIds.has(r.id) ? (
                  <span className="text-xs text-muted-foreground">Flagged</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-amber-600 hover:text-amber-700 hover:bg-amber-50"
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
