// frontend/src/app/clients/[id]/page.tsx
import Link from "next/link"
import { getLatestGeoScore, getClient } from "@/lib/api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { ScoreRing } from "@/components/score/ScoreRing"
import { getScoreBand } from "@/lib/score-utils"

const DIMENSIONS = [
  { key: "ai_citability",         label: "AI Citability",         weight: "40%", manual: false, href: "scan"     },
  { key: "brand_authority",       label: "Brand Authority",       weight: "20%", manual: true,  href: "settings" },
  { key: "content_quality",       label: "Content Quality",       weight: "20%", manual: true,  href: "settings" },
  { key: "technical_foundations", label: "Technical Foundations", weight: "10%", manual: false, href: "toolkit"  },
  { key: "structured_data",       label: "Structured Data",       weight: "10%", manual: false, href: "toolkit"  },
] as const

type DimKey = typeof DIMENSIONS[number]["key"]

const BAND_LABEL: Record<string, string> = {
  excellent: "Excellent",
  good: "Good",
  fair: "Fair",
  developing: "Developing",
  low: "Needs attention",
}

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

  const band = geoScore ? getScoreBand(geoScore.overall_score) : null

  return (
    <div className="space-y-6">
      {/* Overall score hero */}
      <div className="flex flex-col gap-6 rounded-xl border bg-card p-6 shadow-brand sm:flex-row sm:items-center">
        <ScoreRing score={geoScore ? geoScore.overall_score : null} />
        <div className="flex-1">
          <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Overall GEO Score
          </p>
          {geoScore ? (
            <>
              <p className="mt-1 font-display text-2xl font-semibold text-foreground">
                {band ? BAND_LABEL[band.name] : ""}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                How visible this client is across AI search — ChatGPT,
                Perplexity, Gemini and Claude.
              </p>
            </>
          ) : (
            <>
              <p className="mt-1 font-display text-2xl font-semibold text-muted-foreground">
                Awaiting first scan
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Run a scan to measure how this client is seen by AI.
              </p>
              <Link
                href={`/clients/${id}/scan`}
                className="mt-3 inline-flex items-center text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Go to Scan &amp; Visibility →
              </Link>
            </>
          )}
        </div>
      </div>

      {/* 5-dimension breakdown */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Score Breakdown
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {DIMENSIONS.map((dim) => {
            const raw = geoScore ? (geoScore[dim.key as DimKey] as number) : null
            const pct = raw !== null ? Math.max(0, Math.min(100, raw)) : 0
            return (
              <Link
                key={dim.key}
                href={`/clients/${id}/${dim.href}`}
                className="rounded-lg border bg-card p-4 transition-shadow hover:shadow-brand block group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium group-hover:text-primary transition-colors">{dim.label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {dim.weight} weight
                      {dim.manual && (
                        <span className="ml-1.5 italic">· Assessed by SeenBy team</span>
                      )}
                    </p>
                  </div>
                  <ScoreBadge score={raw} />
                </div>
                <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </Link>
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
