// frontend/src/app/clients/[id]/page.tsx
import Link from "next/link"
import { TrendingUp, TrendingDown, Bot } from "lucide-react"
import { getLatestGeoScore, getClient, getActionRecommendations, getTrafficHistory, getIndustryBenchmark } from "@/lib/api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { ScoreRing } from "@/components/score/ScoreRing"
import { IndustryBenchmarkCard } from "@/components/IndustryBenchmarkCard"
import { ActionCenterCard } from "./ActionCenterCard"
import { getScoreBand, getScoreColor } from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type { Client, Platform } from "@/types"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"

function periodKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`
}

const DIMENSIONS = [
  { key: "ai_citability",         label: "AI Citability",         weight: "40%", manual: false, href: "scan",     evidenceKey: null                          },
  { key: "brand_authority",       label: "Brand Authority",       weight: "20%", manual: true,  href: "settings#brand-authority", evidenceKey: "brand_authority_evidence"    },
  { key: "content_quality",       label: "Content Quality",       weight: "20%", manual: true,  href: "settings#content-quality", evidenceKey: "content_quality_evidence"    },
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

// Score-color progress bar fill classes
const BAR_COLOR: Record<string, string> = {
  green:  "bg-score-strong",
  yellow: "bg-score-watch",
  red:    "bg-score-low",
}

// Platform accent colors for the cards (subtle left border tint)
const PLATFORM_ACCENT: Record<Platform, string> = {
  chatgpt:    "border-l-[3px] border-l-emerald-400/70",
  perplexity: "border-l-[3px] border-l-violet-400/70",
  gemini:     "border-l-[3px] border-l-blue-400/70",
  claude:     "border-l-[3px] border-l-orange-400/70",
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
      <div className="relative overflow-hidden flex flex-col gap-6 rounded-xl border bg-card p-6 shadow-brand-lg sm:flex-row sm:items-center">
        {/* Subtle radial glow behind the ring */}
        <div className="pointer-events-none absolute -left-8 -top-8 h-48 w-48 rounded-full bg-primary/[0.06] blur-2xl" />
        <ScoreRing score={geoScore ? geoScore.overall_score : null} />
        <div className="relative flex-1">
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
            Overall GEO Score
          </p>
          {geoScore ? (
            <>
              <p className="mt-1 font-display text-2xl font-semibold text-foreground text-balance">
                {band ? BAND_LABEL[band.name] : ""}
              </p>
              <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
                How visible this client is across AI search — ChatGPT,
                Perplexity, Gemini and Claude.
              </p>
            </>
          ) : (
            <>
              <p className="mt-1 font-display text-2xl font-semibold text-muted-foreground">
                Awaiting first scan
              </p>
              <p className="mt-1.5 text-sm text-muted-foreground">
                Run a scan to measure how this client is seen by AI.
              </p>
              <Link
                href={`/clients/${id}/scan`}
                className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-primary underline-offset-4 hover:underline"
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
          <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
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
                  className={cn(
                    "rounded-lg border bg-card p-4 transition-shadow hover:shadow-brand",
                    unavailable ? "opacity-60" : "",
                    !unavailable && PLATFORM_ACCENT[p],
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold">{PLATFORM_LABELS[p]}</p>
                    {unavailable ? (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        Unavailable
                      </span>
                    ) : seen ? (
                      <span className="rounded-full bg-score-strong-bg px-2 py-0.5 text-[10px] font-semibold text-score-strong">
                        Seen by AI
                      </span>
                    ) : (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        Not seen by AI
                      </span>
                    )}
                  </div>
                  <p className="mt-3 font-display text-2xl font-bold tabular-nums">
                    {unavailable ? "—" : `${Math.round(entry.visibility)}%`}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground/80">
                    {unavailable
                      ? "Platform did not respond"
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
        <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
          Score Breakdown
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {DIMENSIONS.map((dim) => {
            const raw = geoScore ? (geoScore[dim.key as DimKey] as number) : null
            const pct = raw !== null ? Math.max(0, Math.min(100, raw)) : 0
            const band = raw !== null ? getScoreColor(raw) : null
            const evidence = dim.evidenceKey ? client[dim.evidenceKey as keyof Client] as string | null : null
            return (
              <Link
                key={dim.key}
                href={`/clients/${id}/${dim.href}`}
                className="group block rounded-lg border bg-card p-4 transition-all duration-150 hover:border-primary/25 hover:shadow-brand"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold group-hover:text-primary transition-colors">{dim.label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground/70">
                      {dim.weight} weight
                      {dim.manual && (
                        <span className="ml-1.5 italic">· Based on public evidence · Reviewed by SeenBy</span>
                      )}
                    </p>
                  </div>
                  <ScoreBadge score={raw} />
                </div>
                {/* Score bar — thickness increased, uses score-color fill */}
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-700",
                      band ? BAR_COLOR[band] : "bg-primary/30",
                    )}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                {evidence && (
                  <p className="mt-2 text-xs text-muted-foreground/70 line-clamp-2 leading-relaxed">{evidence}</p>
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
      <div className="rounded-lg border bg-card p-5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-4 w-4 text-primary" />
          </span>
          <p className="text-sm font-semibold">AI Visitors This Month</p>
        </div>
        {currentSnap ? (
          <div className="mt-3">
            <p className="font-display text-3xl font-bold tabular-nums text-foreground">
              {currentSnap.ai_visitors.toLocaleString()}
            </p>
            {trafficChange && (
              <p className={cn(
                "mt-1 flex items-center gap-1 text-xs font-semibold",
                trafficChange.up ? "text-score-strong" : "text-score-watch",
              )}>
                {trafficChange.up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                {trafficChange.label}
              </p>
            )}
            <p className="mt-2 text-xs text-muted-foreground/80 leading-relaxed">
              Visitors arriving via ChatGPT, Perplexity, Gemini and Claude — entered manually by the SeenBy team.
            </p>
          </div>
        ) : (
          <div className="mt-3">
            <p className="font-display text-2xl font-semibold text-muted-foreground">
              Awaiting entry
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Add this month&apos;s AI-referral visitor count in{" "}
              <Link href={`/clients/${id}/settings`} className="text-primary underline-offset-4 hover:underline font-medium">
                Settings
              </Link>
              .
            </p>
          </div>
        )}
      </div>

      {geoScore && <ActionCenterCard clientId={id} initialActions={actions} />}

      {geoScore && (() => {
        const computedAt = new Date(geoScore.computed_at)
        const daysSinceComputed = (Date.now() - computedAt.getTime()) / (1000 * 60 * 60 * 24)
        const isStale = daysSinceComputed > client.scan_cadence_days
        const formatted = computedAt.toLocaleDateString("en-MY", {
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
        return (
          <p className={cn("text-xs", isStale ? "text-score-watch font-medium" : "text-muted-foreground/50")}>
            Score computed {formatted}
            {isStale && (
              <span className="ml-1">
                — {Math.floor(daysSinceComputed)} days ago. A new scan may be due.
              </span>
            )}
          </p>
        )
      })()}
    </div>
  )
}
