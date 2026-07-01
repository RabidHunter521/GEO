// frontend/src/app/view/[token]/page.tsx
// Read-only overview, sequenced as a narrative: where you stand → what
// changed → the breakdown → what we're working on → trends. Zero mutations.
import Link from "next/link"
import { notFound } from "next/navigation"
import { AlertCircle, ArrowRight, Radar, Sparkles } from "lucide-react"
import {
  getViewOverview,
  getViewActions,
  getViewIssues,
  getViewScan,
  getViewProgress,
} from "@/lib/view-api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { ScoreRing } from "@/components/score/ScoreRing"
import { ScoreHistoryChart } from "@/components/view/ScoreHistoryChart"
import { AiTrafficChart } from "@/components/view/AiTrafficChart"
import { AiPipelineValueCard } from "@/components/view/AiPipelineValueCard"
import { ClientProgressList } from "@/components/view/ClientProgressList"
import { ProofCardList } from "@/components/view/ProofCardList"
import { DimensionInfo } from "@/components/view/DimensionInfo"
import { PlatformIcon } from "@/components/view/PlatformIcon"
import { SectionHeading } from "@/components/view/SectionHeading"
import { IndustryBenchmarkCard } from "@/components/IndustryBenchmarkCard"
import { getScoreBand, getScoreColor, type ScoreColor } from "@/lib/score-utils"
import { cn, joinWithAnd } from "@/lib/utils"
import type { ClientViewScore } from "@/types"

const DIMENSIONS = [
  {
    key: "ai_visibility", label: "AI Visibility", weight: "40%", manual: false,
    description:
      "Measures how often your brand appears, is seen, or is recommended by AI search engines such as ChatGPT, Gemini, Claude, and Perplexity when users ask relevant questions.",
  },
  {
    key: "brand_authority", label: "Brand Authority", weight: "20%", manual: true,
    description:
      "Evaluates your brand's credibility, reputation, and trustworthiness across the web based on brand presence, backlinks, reviews, and industry recognition.",
  },
  {
    key: "content_quality", label: "Content Quality", weight: "20%", manual: true,
    description:
      "Assesses how well your website content answers user questions through accuracy, depth, relevance, freshness, and expertise.",
  },
  {
    key: "technical_foundations", label: "Technical Foundations", weight: "10%", manual: false,
    description:
      "Reviews the technical health of your website, including page speed, crawlability, mobile experience, security, and accessibility.",
  },
  {
    key: "structured_data", label: "Structured Data", weight: "10%", manual: false,
    description:
      "Measures the implementation and quality of schema markup that helps search engines and AI systems better understand your content, products, services, and business information.",
  },
] as const

type DimKey = typeof DIMENSIONS[number]["key"]

const BAND_LABEL: Record<string, string> = {
  excellent: "Excellent",
  good: "Good",
  fair: "Fair",
  developing: "Developing",
  low: "Needs attention",
}

// Band chip on the hero — colored to match the 3-band traffic light so the
// label reinforces the ring color instead of floating as neutral text.
const BAND_CHIP: Record<ScoreColor, string> = {
  green: "bg-score-strong-bg text-score-strong",
  yellow: "bg-score-watch-bg text-score-watch",
  red: "bg-score-low-bg text-score-low",
}

// Score-aware breakdown bar fill — a row of identical violet bars hides which
// dimensions are weak; coloring by score lets a client read strength at a glance.
const BAR_CLASS: Record<ScoreColor, string> = {
  green: "bar-strong",
  yellow: "bar-watch",
  red: "bar-low",
}

const PRIORITY_CLASS: Record<string, string> = {
  high: "bg-score-low-bg text-score-low border-score-low/25",
  medium: "bg-score-watch-bg text-score-watch border-score-watch/30",
  low: "bg-muted text-muted-foreground border-border",
}

export default async function ViewOverviewPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [overview, actions, issues, scan, progress] = await Promise.all([
    getViewOverview(token),
    getViewActions(token),
    getViewIssues(token),
    getViewScan(token),
    getViewProgress(token),
  ])
  if (!overview) notFound()

  // Prospects get a stripped-down overview: just the score hero and the
  // per-platform visibility. The deeper breakdown, benchmark, action plan and
  // trends are reserved for converted clients (who have manual + competitor data).
  const isProspect = overview.profile.is_prospect

  const score = overview.latest_score
  const band = score ? getScoreBand(score.overall_score) : null
  const scoreColor = score ? getScoreColor(score.overall_score) : null
  // Name the platforms actually queried for this client rather than hardcoding
  // all four — a prospect may only run on a couple.
  const platformNames = joinWithAnd(overview.platforms.map((p) => p.platform_label))

  // Plain-English headline derived from existing data.
  const seenCount = scan ? scan.results.filter((r) => r.seen_by_ai).length : 0
  const totalCount = scan ? scan.results.length : 0
  const seenPlatforms = overview.platforms.filter((p) => p.seen_by_ai).length
  let headline = ""
  if (score) {
    if (totalCount > 0) {
      headline = `You're seen by AI in ${seenCount} of ${totalCount} buyer questions`
    } else if (overview.platforms.length > 0) {
      headline = `You're seen by AI on ${seenPlatforms} of ${overview.platforms.length} AI platforms`
    } else {
      headline = band ? BAND_LABEL[band.name] : ""
    }
    if (!isProspect && overview.benchmark) {
      headline += ` — top ${overview.benchmark.top_percent}% of ${overview.benchmark.industry}`
    }
  }

  return (
    <div className="space-y-6">
      {/* 1. Hero — score + plain-English headline + freshness. Elevated above
          the rest with atmosphere and a soft glow so it reads as THE headline. */}
      <section
        className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-6 shadow-brand-lg sm:p-8"
        style={{ animationDelay: "0ms" }}
      >
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
          <ScoreRing score={score ? score.overall_score : null} size={148} />
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Your AI Visibility Score
              </p>
              {band && scoreColor && (
                <span
                  className={cn(
                    "rounded-full px-2.5 py-0.5 text-xs font-semibold",
                    BAND_CHIP[scoreColor],
                  )}
                >
                  {BAND_LABEL[band.name]}
                </span>
              )}
            </div>
            {score ? (
              <>
                <p className="mt-2 text-balance font-display text-2xl font-semibold leading-snug text-foreground sm:text-[1.7rem]">
                  {headline}
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  How visible you are across AI search
                  {platformNames ? ` — ${platformNames}` : ""}.
                </p>
                <p className="mt-3 text-xs text-muted-foreground">
                  Last updated{" "}
                  {new Date(score.computed_at).toLocaleDateString("en-MY", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                  {/* Older than the freshness window: reassure with the next
                      scheduled check-in instead of leaving a bare stale date. */}
                  {overview.is_stale && overview.next_check_due && (
                    <span className="ml-1.5 inline-flex items-center rounded-full bg-primary/5 px-2 py-0.5 font-medium text-primary">
                      Next visibility check due{" "}
                      {new Date(overview.next_check_due).toLocaleDateString("en-MY", {
                        day: "numeric",
                        month: "short",
                      })}
                    </span>
                  )}
                </p>
                {!isProspect && overview.fixed_this_month > 0 && (
                  <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-score-strong-bg px-3 py-1 text-xs font-semibold text-score-strong">
                    <Sparkles className="h-3.5 w-3.5" />
                    {overview.fixed_this_month} item
                    {overview.fixed_this_month === 1 ? "" : "s"} we fixed this month
                  </p>
                )}
              </>
            ) : (
              <>
                <p className="mt-2 flex items-center gap-2 font-display text-2xl font-semibold leading-snug text-foreground">
                  <Radar className="h-6 w-6 shrink-0 text-primary" />
                  Your first scan is being prepared
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  Your SeenBy team is setting up your first AI visibility scan.
                  Results will appear here soon.
                </p>
              </>
            )}
          </div>
        </div>
      </section>

      {/* 2. What Changed — promoted: the most human, most flattering piece */}
      {!isProspect && overview.change_narrative && (
        <section
          className="reveal rounded-xl border border-primary/15 bg-primary/5 p-5"
          style={{ animationDelay: "60ms" }}
        >
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            What Changed
            {overview.change_narrative_period ? ` — ${overview.change_narrative_period}` : ""}
          </h2>
          <p className="text-sm leading-relaxed text-foreground">{overview.change_narrative}</p>
        </section>
      )}

      {/* 2.25 Straight from AI — verbatim proof (clients only) */}
      {!isProspect && overview.proof_cards && overview.proof_cards.length > 0 && (
        <section className="reveal" style={{ animationDelay: "120ms" }}>
          <ProofCardList cards={overview.proof_cards} />
        </section>
      )}

      {/* 2.5 What it's worth — the one money number (clients only) */}
      {!isProspect && overview.traffic_value && (
        <section className="reveal" style={{ animationDelay: "150ms" }}>
          <AiPipelineValueCard value={overview.traffic_value} />
        </section>
      )}

      {/* 3. Where you stand — benchmark + per-platform visibility */}
      {!isProspect && overview.benchmark && (
        <section className="reveal" style={{ animationDelay: "180ms" }}>
          <IndustryBenchmarkCard
            industry={overview.benchmark.industry}
            topPercent={overview.benchmark.top_percent}
            peerCount={overview.benchmark.peer_count}
            industryAverage={overview.benchmark.industry_average}
          />
        </section>
      )}

      {overview.platforms.length > 0 && (
        <section className="reveal" style={{ animationDelay: "210ms" }}>
          <SectionHeading>Seen by AI — by Platform</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {overview.platforms.map((p) => {
              const unavailable = p.visibility_frequency === null
              return (
                <div
                  key={p.platform_label}
                  className={cn(
                    "card-lift relative overflow-hidden rounded-xl border p-4",
                    unavailable ? "bg-muted/30" : "bg-card",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "absolute inset-x-0 top-0 h-0.5",
                      unavailable
                        ? "bg-transparent"
                        : p.seen_by_ai
                          ? "bg-score-strong"
                          : "bg-muted-foreground/25",
                    )}
                  />
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <PlatformIcon label={p.platform_label} />
                      <p className="truncate text-sm font-medium">{p.platform_label}</p>
                    </div>
                    {unavailable ? (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        Checking soon
                      </span>
                    ) : p.seen_by_ai ? (
                      <span className="rounded-full bg-score-strong-bg px-2 py-0.5 text-xs font-medium text-score-strong">
                        Seen by AI
                      </span>
                    ) : (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        Not seen by AI
                      </span>
                    )}
                  </div>
                  <p className="mt-2 font-display text-2xl font-bold tabular-nums">
                    {unavailable ? "—" : `${Math.round(p.visibility_frequency!)}%`}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {unavailable
                      ? "This platform will be checked on the next scan"
                      : "visibility frequency"}
                  </p>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 4. Score breakdown — the 5 dimensions (clients only) */}
      {!isProspect && (
        <section className="reveal" style={{ animationDelay: "240ms" }}>
          <SectionHeading>Score Breakdown</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2">
            {DIMENSIONS.map((dim) => {
              const raw = score ? (score[dim.key as DimKey & keyof ClientViewScore] as number) : null
              const pct = raw !== null ? Math.max(0, Math.min(100, raw)) : 0
              const barClass = raw !== null ? BAR_CLASS[getScoreColor(raw)] : "bar-primary"
              return (
                <div key={dim.key} className="card-lift rounded-xl border bg-card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <DimensionInfo label={dim.label} description={dim.description} />
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {dim.weight} weight
                        {dim.manual && (
                          <span className="ml-1.5 italic">· Based on public evidence · Reviewed by SeenBy</span>
                        )}
                      </p>
                    </div>
                    <ScoreBadge score={raw} />
                  </div>
                  <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn("h-full rounded-full transition-all", barClass)}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  {dim.key === "brand_authority" && score && (score.brand_authority_evidence ?? []).length > 0 && (
                    <ul className="ml-4 mt-1 list-disc text-sm text-muted-foreground">
                      {(score.brand_authority_evidence ?? []).map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  )}
                  {dim.key === "content_quality" && score && (score.content_quality_evidence ?? []).length > 0 && (
                    <ul className="ml-4 mt-1 list-disc text-sm text-muted-foreground">
                      {(score.content_quality_evidence ?? []).map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 5. What we're working on — condensed issues + top next steps (clients only) */}
      {!isProspect && ((issues && issues.length > 0) || (actions && actions.length > 0)) && (
        <section
          className="reveal rounded-xl border bg-card p-5"
          style={{ animationDelay: "270ms" }}
        >
          <SectionHeading
            action={
              overview.has_content_plan ? (
                <Link
                  href={`/view/${token}/content-plan`}
                  className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
                >
                  See the full plan
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              ) : undefined
            }
          >
            What We&apos;re Working On
          </SectionHeading>

          {issues && issues.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {issues.flatMap((group) =>
                group.issues.slice(0, 1).map((issue) => (
                  <li
                    key={`${group.dimension}-${issue}`}
                    className="flex items-start gap-2 text-sm text-muted-foreground"
                  >
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-score-watch" />
                    {issue}
                  </li>
                )),
              )}
            </ul>
          )}

          {actions && actions.length > 0 && (
            <ul className="mt-3 space-y-2">
              {actions.slice(0, 3).map((a, i) => (
                <li
                  key={`${a.generated_at}-${i}`}
                  className="flex items-start gap-3 rounded-md border bg-background p-3"
                >
                  <span
                    className={cn(
                      "mt-0.5 shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                      PRIORITY_CLASS[a.priority] ?? PRIORITY_CLASS.low,
                    )}
                  >
                    {a.priority}
                  </span>
                  <p className="text-sm">{a.action_text}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* 5.5 What we're fixing — remediation loop with status (clients only) */}
      {!isProspect && progress && progress.length > 0 && (
        <section className="reveal" style={{ animationDelay: "300ms" }}>
          <ClientProgressList items={progress} />
        </section>
      )}

      {/* 6. Trends — score history + AI traffic (clients only) */}
      {!isProspect && (
        <section className="reveal space-y-6" style={{ animationDelay: "330ms" }}>
          <ScoreHistoryChart points={overview.score_history} />
          <AiTrafficChart points={overview.traffic} />
        </section>
      )}
    </div>
  )
}
