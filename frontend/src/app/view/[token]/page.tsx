// frontend/src/app/view/[token]/page.tsx
// Read-only overview: overall score, dimension breakdown, AI visitor
// traffic, score history, and recommended actions. Zero mutations.
import { notFound } from "next/navigation"
import { TrendingUp, TrendingDown, AlertCircle } from "lucide-react"
import { getViewOverview, getViewActions, getViewIssues } from "@/lib/view-api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { ScoreRing } from "@/components/score/ScoreRing"
import { ScoreHistoryChart } from "@/components/view/ScoreHistoryChart"
import { DimensionInfo } from "@/components/view/DimensionInfo"
import { getScoreBand } from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type { ClientViewScore } from "@/types"

function periodKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`
}

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
  const [overview, actions, issues] = await Promise.all([
    getViewOverview(token),
    getViewActions(token),
    getViewIssues(token),
  ])
  if (!overview) notFound()

  const score = overview.latest_score
  const band = score ? getScoreBand(score.overall_score) : null

  const now = new Date()
  const currentSnap = overview.traffic.find((t) => t.period.slice(0, 10) === periodKey(now))
  const prevSnap = overview.traffic.find(
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
        <ScoreRing score={score ? score.overall_score : null} />
        <div className="flex-1">
          <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Your AI Visibility Score
          </p>
          {score ? (
            <>
              <p className="mt-1 font-display text-2xl font-semibold text-foreground">
                {band ? BAND_LABEL[band.name] : ""}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                How visible you are across AI search — ChatGPT, Perplexity,
                Gemini and Claude.
              </p>
            </>
          ) : (
            <>
              <p className="mt-1 font-display text-2xl font-semibold text-muted-foreground">
                Your first scan is being prepared
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Your SeenBy team is setting up your first AI visibility scan.
                Results will appear here soon.
              </p>
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
            const raw = score ? (score[dim.key as DimKey & keyof ClientViewScore] as number) : null
            const pct = raw !== null ? Math.max(0, Math.min(100, raw)) : 0
            return (
              <div key={dim.key} className="rounded-lg border bg-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <DimensionInfo label={dim.label} description={dim.description} />
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
              </div>
            )
          })}
        </div>
      </div>

      {/* Issues found that impact the GEO score */}
      {issues && issues.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Issues Found That Impact Your GEO Score
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {issues.map((group) => (
              <div key={group.dimension} className="rounded-lg border bg-card p-4">
                <p className="text-sm font-medium">{group.dimension_label}</p>
                <ul className="mt-2 space-y-1.5">
                  {group.issues.map((issue) => (
                    <li key={issue} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-score-watch" />
                      {issue}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Identified from your latest scan. The SeenBy team is working on
            these — see Recommended Next Steps below.
          </p>
        </div>
      )}

      {/* Score history */}
      <ScoreHistoryChart points={overview.score_history} />

      {/* AI Referral Traffic */}
      {currentSnap && (
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm font-medium">AI Visitors This Month</p>
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
            Visitors arriving at your website via ChatGPT, Perplexity, Gemini
            and Claude — tracked by the SeenBy team.
          </p>
        </div>
      )}

      {/* Recommended actions — read-only */}
      {actions && actions.length > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm font-medium">Recommended Next Steps</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            What the SeenBy team is focusing on to improve your visibility.
          </p>
          <ul className="mt-3 space-y-2">
            {actions.map((a, i) => (
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
        </div>
      )}

      {score && (
        <p className="text-xs text-muted-foreground">
          Score updated{" "}
          {new Date(score.computed_at).toLocaleDateString("en-MY", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </p>
      )}
    </div>
  )
}
