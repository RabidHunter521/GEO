// frontend/src/app/clients/[id]/page.tsx
import { getLatestGeoScore, getClient } from "@/lib/api"
import { ScoreBadge } from "@/components/score/ScoreBadge"

const DIMENSIONS = [
  { key: "ai_citability",         label: "AI Citability",         weight: "40%", manual: false },
  { key: "brand_authority",       label: "Brand Authority",       weight: "20%", manual: true  },
  { key: "content_quality",       label: "Content Quality",       weight: "20%", manual: true  },
  { key: "technical_foundations", label: "Technical Foundations", weight: "10%", manual: false },
  { key: "structured_data",       label: "Structured Data",       weight: "10%", manual: false },
] as const

type DimKey = typeof DIMENSIONS[number]["key"]

export default async function ClientOverviewPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const [, geoScore] = await Promise.all([
    getClient(id),
    getLatestGeoScore(id),
  ])

  return (
    <div className="space-y-6">
      {/* Overall score */}
      <div className="flex items-center gap-4 p-5 rounded-lg border bg-card">
        <div className="flex-1">
          <p className="text-sm text-muted-foreground font-medium">
            Overall GEO Score
          </p>
          {geoScore ? (
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-4xl font-bold">
                {geoScore.overall_score.toFixed(0)}
              </span>
              <span className="text-muted-foreground">/ 100</span>
            </div>
          ) : (
            <p className="text-2xl font-semibold text-muted-foreground mt-1">
              Awaiting first scan
            </p>
          )}
        </div>
        {geoScore && (
          <ScoreBadge score={geoScore.overall_score} className="text-sm px-3 py-1" />
        )}
      </div>

      {/* 5-dimension breakdown */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
          Score Breakdown
        </h2>
        <div className="space-y-2">
          {DIMENSIONS.map((dim) => {
            const raw = geoScore ? (geoScore[dim.key as DimKey] as number) : null
            return (
              <div
                key={dim.key}
                className="flex items-center justify-between rounded-md border px-4 py-3 bg-card"
              >
                <div>
                  <p className="text-sm font-medium">{dim.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {dim.weight} weight
                    {dim.manual && (
                      <span className="ml-2 italic">· Assessed by SeenBy team</span>
                    )}
                  </p>
                </div>
                <ScoreBadge score={raw} />
              </div>
            )
          })}
        </div>
      </div>

      {geoScore && (
        <p className="text-xs text-muted-foreground">
          Score computed{" "}
          {new Date(geoScore.computed_at).toLocaleDateString("en-MY", {
            day: "numeric",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      )}
    </div>
  )
}
