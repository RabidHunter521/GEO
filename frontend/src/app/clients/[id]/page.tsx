// frontend/src/app/clients/[id]/page.tsx
import Link from "next/link"
import { TrendingUp, TrendingDown } from "lucide-react"
import { getLatestGeoScore, getClient, getActionRecommendations, getTrafficHistory, getIndustryBenchmark } from "@/lib/api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { ScoreRing } from "@/components/score/ScoreRing"
import { IndustryBenchmarkCard } from "@/components/IndustryBenchmarkCard"
import { ActionCenterCard } from "./ActionCenterCard"
import { getScoreBand } from "@/lib/score-utils"
import type { Client, Platform } from "@/types"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"

function periodKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`
}

const DIMENSIONS = [
  { key: "ai_citability",         label: "AI Citability",         weight: "40%", manual: false, href: "scan",     evidenceKey: null                          },
  { key: "brand_authority",       label: "Brand Authority",       weight: "20%", manual: true,  href: "settings", evidenceKey: "brand_authority_evidence"    },
  { key: "content_quality",       label: "Content Quality",       weight: "20%", manual: true,  href: "settings", evidenceKey: "content_quality_evidence"    },
  { key: "technical_foundations", label: "Technical Foundations", weight: "10%", manual: false, href: "toolkit",  evidenceKey: null                          },
  { key: "structured_data",       label: "Structured Data",       weight: "10%", manual: false, href: "toolkit",  evidenceKey: null                          },
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
  const [client, geoScore, actions, trafficHistory, benchmark] = await Promise.all([
    getClient(id),
    getLatestGeoScore(id),
    getActionRecommendations(id),
    getTrafficHistory(id),
    getIndustryBenchmark(id).catch(() => null),
  ])

  const band = geoScore ? getScoreBand(geoScore.overall_score) : null

  const now = new Date()
  const currentSnap = trafficHistory.find((t) => t.period.slice(0, 10) === periodKey(now))
  const prevSnap = trafficHistory.find(
    (t) => t.period.slice(0, 10) === periodKey(new Date(now.getFullYear(), now.getMonth() - 1, 1))
  )
  let trafficChange: { label: string; up: boolean } | null = null
  if (currentSnap && prevSnap) {
    if (prevSnap.ai_visitors > 0) {
      const pct = Math.round(((currentSnap.ai_visitors - prevSnap.ai_visitors) / prevSnap.ai_visitors) * 100)
      trafficChange = { label: `${pct >= 0 ? "+" : ""}${pct}% vs last month`, up: pct >= 0 }
    } else if (currentSnap.ai_visitors > 0) {
      trafficChange = { label: "New vs last month", up: true }
    }
  }

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

      {/* Seen by AI — per platform */}
      {geoScore?.platform_breakdown && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Seen by AI — by Platform
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {SCAN_PLATFORMS.filter((p) => geoScore.platform_breakdown?.[p]).map((p: Platform) => {
              const entry = geoScore.platform_breakdown![p]!
              const unavailable = entry.status !== "ok"
              const seen = entry.detected > 0
              return (
                <div
                  key={p}
                  className={`rounded-lg border p-4 ${unavailable ? "bg-muted/30" : "bg-card"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{PLATFORM_LABELS[p]}</p>
                    {unavailable ? (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        Unavailable
                      </span>
                    ) : seen ? (
                      <span className="rounded-full bg-score-strong-bg px-2 py-0.5 text-xs font-medium text-score-strong">
                        Seen by AI
                      </span>
                    ) : (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        Not seen by AI
                      </span>
                    )}
                  </div>
                  <p className="mt-2 font-display text-xl font-bold tabular-nums">
                    {unavailable ? "—" : `${Math.round(entry.visibility)}%`}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {unavailable
                      ? "Platform did not respond during the latest scan"
                      : `visibility frequency · ${entry.detected}/${entry.queries} queries`}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 5-dimension breakdown */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Score Breakdown
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {DIMENSIONS.map((dim) => {
            const raw = geoScore ? (geoScore[dim.key as DimKey] as number) : null
            const pct = raw !== null ? Math.max(0, Math.min(100, raw)) : 0
            const evidence = dim.evidenceKey ? client[dim.evidenceKey as keyof Client] as string | null : null
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
                {evidence && (
                  <p className="mt-2 text-xs text-muted-foreground line-clamp-2">{evidence}</p>
                )}
              </Link>
            )
          })}
        </div>
      </div>

      {/* Industry benchmark */}
      {benchmark && (
        <IndustryBenchmarkCard
          industry={benchmark.industry}
          topPercent={benchmark.top_percent}
          peerCount={benchmark.peer_count}
          industryAverage={benchmark.industry_average}
          clientScore={benchmark.client_score}
          rank={benchmark.rank}
        />
      )}

      {/* AI Referral Traffic */}
      <div className="rounded-lg border bg-card p-4">
        <p className="text-sm font-medium">AI Visitors This Month</p>
        {currentSnap ? (
          <>
            <p className="mt-1 font-display text-2xl font-semibold text-foreground">
              {currentSnap.ai_visitors.toLocaleString()}
            </p>
            {trafficChange && (
              <p className={`mt-1 flex items-center gap-1 text-xs font-medium ${trafficChange.up ? "text-score-strong" : "text-score-watch"}`}>
                {trafficChange.up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                {trafficChange.label}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Visitors arriving via ChatGPT, Perplexity, Gemini and Claude — entered manually by the SeenBy team.
            </p>
          </>
        ) : (
          <>
            <p className="mt-1 font-display text-2xl font-semibold text-muted-foreground">
              Awaiting entry
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Add this month&apos;s AI-referral visitor count in{" "}
              <Link href={`/clients/${id}/settings`} className="text-primary underline-offset-4 hover:underline">
                Settings
              </Link>
              .
            </p>
          </>
        )}
      </div>

      {geoScore && <ActionCenterCard clientId={id} initialActions={actions} />}

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
