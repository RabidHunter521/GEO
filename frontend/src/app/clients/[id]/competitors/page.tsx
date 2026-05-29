import Link from "next/link"
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { getCompetitorIntelligence } from "@/lib/api"

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

  let data = null
  try {
    data = await getCompetitorIntelligence(id)
  } catch {
    // backend down — show error state
  }

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

  const winningCount = data.competitors.filter((c) => c.is_winning).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">Competitor Intelligence</h2>
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
            className="gap-1.5 text-amber-700 border-amber-300 bg-amber-50"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            {winningCount} competitor{winningCount > 1 ? "s" : ""} winning
          </Badge>
        )}
      </div>

      {/* No scan yet */}
      {data.client_ai_citability === null && (
        <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Run your first scan to see competitor intelligence</p>
          <p className="text-sm mt-1">
            Go to{" "}
            <Link href={`/clients/${id}/scan`} className="underline underline-offset-4">
              Scan &amp; Visibility
            </Link>{" "}
            and trigger a scan.
          </p>
        </div>
      )}

      {/* Client score summary */}
      {data.client_ai_citability !== null && (
        <div className="rounded-lg border px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Your AI visibility</p>
            <p className="text-2xl font-bold tabular-nums">
              {data.client_ai_citability.toFixed(0)}
              <span className="text-base font-normal text-muted-foreground">%</span>
            </p>
          </div>
          <p className="text-sm text-muted-foreground">visibility frequency</p>
        </div>
      )}

      {/* Competitor cards */}
      <div className="space-y-4">
        {data.competitors.map((comp) => (
          <div key={comp.id} className="rounded-lg border overflow-hidden">
            {/* Card header */}
            <div className="flex items-start justify-between px-5 py-4 bg-muted/20">
              <div>
                <p className="font-semibold">{comp.name}</p>
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
                  <Badge className="bg-amber-100 text-amber-800 border-amber-200 gap-1 shrink-0">
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

            {/* Query breakdown */}
            {comp.queries.length > 0 ? (
              <div className="divide-y">
                {comp.queries.map((q) => (
                  <div
                    key={`${comp.id}-${q.category}`}
                    className="flex items-center justify-between px-5 py-3 text-sm"
                  >
                    <div className="flex items-center gap-3">
                      {q.brand_detected ? (
                        <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                      )}
                      <span className="text-muted-foreground font-medium">
                        {CATEGORY_LABELS[q.category] ?? q.category}
                      </span>
                    </div>
                    <span
                      className={
                        q.brand_detected
                          ? "text-green-700 font-medium"
                          : "text-muted-foreground"
                      }
                    >
                      {q.brand_detected ? "Seen by AI" : "Not yet seen by AI"}
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
