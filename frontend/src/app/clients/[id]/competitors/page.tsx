import Link from "next/link"
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { getCompetitorIntelligence, getCompetitorTrends, getWinLoss, getProvenance, getShareOfSourceHistory } from "@/lib/api"
import { VisibilityTrendChart } from "@/components/competitors/VisibilityTrendChart"
import { WinLossSection } from "@/components/competitors/WinLossSection"
import { ShareOfSourceSection } from "@/components/competitors/ShareOfSourceSection"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"

interface Props {
  params: Promise<{ id: string }>
}

const CATEGORY_LABELS: Record<string, string> = {
  brand: "Brand",
  comparison: "Comparison",
  recommendation: "Recommendation",
  local: "Local",
}

export default async function CompetitorsPage({ params }: Props) {
  const { id } = await params

  const [data, winLoss, trends, provenance, shareOfSourceHistory] = await Promise.all([
    getCompetitorIntelligence(id).catch(() => null),
    getWinLoss(id).catch(() => null),
    getCompetitorTrends(id).catch(() => null),
    getProvenance(id).catch(() => null),
    getShareOfSourceHistory(id).catch(() => []),
  ])

  if (!data) {
    return (
      <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
        <p className="font-medium">Unable to load competitor data</p>
        <p className="text-sm mt-1">Check that the backend is running and try again.</p>
      </div>
    )
  }

  if (data.competitors.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
        <p className="font-medium">No competitors added yet</p>
        <p className="text-sm mt-1">
          Add up to 5 competitors in{" "}
          <Link href={`/clients/${id}/settings`} className="underline underline-offset-4">
            settings
          </Link>{" "}
          to start tracking their visibility.
        </p>
      </div>
    )
  }

  // No scan yet — show early return with competitor name stubs
  if (data.client_ai_citability === null) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Competitor Intelligence
          </h2>
        </div>
        <div className="rounded-lg border border-dashed bg-card/50 p-8 text-center text-muted-foreground">
          <p className="font-medium">Run your first scan to see competitor intelligence</p>
          <p className="text-sm mt-1">
            Go to{" "}
            <Link href={`/clients/${id}/scan`} className="underline underline-offset-4">
              Scan &amp; Visibility
            </Link>{" "}
            and trigger a scan.
          </p>
        </div>
        <div className="space-y-4">
          {data.competitors.map((comp) => (
            <div key={comp.id} className="overflow-hidden rounded-lg border bg-card">
              <div className="flex items-start justify-between border-b bg-muted/30 px-5 py-4">
                <div>
                  <p className="font-semibold">{comp.name ?? "Unnamed competitor"}</p>
                  {comp.website && (
                    <p className="text-xs text-muted-foreground mt-0.5">{comp.website}</p>
                  )}
                </div>
              </div>
              <div className="px-5 py-4 text-sm text-muted-foreground">
                No scan data yet — run a scan to see this competitor&apos;s visibility.
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Full data view — only reached when client_ai_citability is not null
  const winningCount = data.competitors.filter((c) => c.is_winning).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Competitor Intelligence
          </h2>
          {data.last_scan_at && (
            <p className="text-sm text-muted-foreground mt-1">
              Based on scan from{" "}
              {new Date(data.last_scan_at).toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </p>
          )}
        </div>
        {winningCount > 0 && (
          <Badge
            variant="outline"
            className="gap-1.5 text-score-watch border-score-watch/30 bg-score-watch-bg"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            {winningCount} competitor{winningCount > 1 ? "s" : ""} winning
          </Badge>
        )}
      </div>

      {/* Client score summary */}
      <div className="rounded-xl border bg-card px-5 py-4 shadow-brand">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Your AI visibility</p>
            <p className="font-display text-3xl font-bold tabular-nums text-primary">
              {data.client_ai_citability.toFixed(0)}
              <span className="text-base font-normal text-muted-foreground">%</span>
            </p>
          </div>
          <p className="text-sm text-muted-foreground">visibility frequency</p>
        </div>
        {Object.keys(data.client_platform_visibility).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
            {SCAN_PLATFORMS.filter((p) => data.client_platform_visibility[p] != null).map((p) => (
              <span
                key={p}
                className="rounded-full border bg-muted/30 px-2.5 py-1 text-xs tabular-nums"
              >
                {PLATFORM_LABELS[p]}:{" "}
                <span className="font-semibold">
                  {data.client_platform_visibility[p]!.toFixed(0)}%
                </span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Visibility trends */}
      {trends && trends.scans.length >= 2 && (
        <VisibilityTrendChart
          dates={trends.scans.map((s) => s.completed_at)}
          series={[
            { name: trends.client.name, isYou: true, points: trends.client.points },
            ...trends.competitors.map((c) => ({
              name: c.name,
              isYou: false,
              points: c.points,
            })),
          ]}
        />
      )}

      {/* Win/loss by query */}
      {winLoss && <WinLossSection clientId={id} data={winLoss} />}

      {/* Share of Source */}
      {provenance && <ShareOfSourceSection data={provenance} history={shareOfSourceHistory} />}

      {/* Competitor cards */}
      <div className="space-y-4">
        {data.competitors.map((comp) => (
          <div key={comp.id} className="overflow-hidden rounded-lg border bg-card">
            {/* Card header */}
            <div className="flex items-start justify-between border-b bg-muted/30 px-5 py-4">
              <div>
                <p className="font-semibold">{comp.name ?? "Unnamed competitor"}</p>
                {comp.website && (
                  <p className="text-xs text-muted-foreground mt-0.5">{comp.website}</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-xl font-bold tabular-nums">
                    {comp.ai_citability.toFixed(0)}
                    <span className="text-sm font-normal text-muted-foreground">%</span>
                  </p>
                  <p className="text-xs text-muted-foreground">visibility frequency</p>
                </div>
                {comp.is_winning ? (
                  <Badge className="gap-1 shrink-0 border-score-watch/30 bg-score-watch-bg text-score-watch">
                    <AlertTriangle className="h-3 w-3" />
                    Your competitors are winning here
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-muted-foreground gap-1 shrink-0">
                    Behind you
                  </Badge>
                )}
              </div>
            </div>

            {/* Per-platform comparison */}
            {Object.keys(comp.platform_visibility).length > 0 && (
              <div className="flex flex-wrap gap-2 border-b bg-muted/10 px-5 py-3">
                {SCAN_PLATFORMS.filter((p) => comp.platform_visibility[p] != null).map((p) => {
                  const winning = comp.winning_platforms.includes(p)
                  return (
                    <span
                      key={p}
                      className={`rounded-full border px-2.5 py-1 text-xs tabular-nums ${
                        winning
                          ? "border-score-watch/30 bg-score-watch-bg text-score-watch font-medium"
                          : "bg-muted/30"
                      }`}
                    >
                      {PLATFORM_LABELS[p]}: {comp.platform_visibility[p]!.toFixed(0)}%
                      {winning && " · winning here"}
                    </span>
                  )
                })}
              </div>
            )}

            {/* Query breakdown */}
            {comp.queries.length > 0 ? (
              <div className="divide-y">
                {comp.queries.map((q) => (
                  <div
                    key={`${comp.id}-${q.platform}-${q.category}-${q.query_text}`}
                    className="flex items-center justify-between px-5 py-3 text-sm"
                  >
                    <div className="flex items-center gap-3">
                      {q.brand_detected ? (
                        <CheckCircle className="h-4 w-4 text-score-strong shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                      )}
                      <span className="text-xs font-medium w-20 shrink-0">
                        {PLATFORM_LABELS[q.platform] ?? q.platform}
                      </span>
                      <span className="text-muted-foreground font-medium">
                        {CATEGORY_LABELS[q.category] ?? q.category}
                      </span>
                    </div>
                    <span
                      className={
                        q.brand_detected
                          ? "text-score-strong font-medium"
                          : "text-muted-foreground"
                      }
                    >
                      {q.brand_detected ? "Seen by AI" : "Not seen by AI"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-5 py-4 text-sm text-muted-foreground">
                No scan data for this competitor yet. Run a scan to see their results.
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
