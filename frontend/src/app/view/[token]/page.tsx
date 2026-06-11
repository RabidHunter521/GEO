// frontend/src/app/view/[token]/page.tsx
// Read-only overview: overall score, dimension breakdown, AI visitor
// traffic, score history, and recommended actions. Zero mutations.
import { notFound } from "next/navigation"
import { TrendingUp, TrendingDown } from "lucide-react"
import { getViewOverview, getViewActions } from "@/lib/view-api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { ScoreRing } from "@/components/score/ScoreRing"
import { ScoreHistoryChart } from "@/components/view/ScoreHistoryChart"
import { getScoreBand } from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type { ClientViewScore } from "@/types"

function periodKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`
}

const DIMENSIONS = [
  { key: "ai_visibility",         label: "AI Visibility",         weight: "40%", manual: false },
  { key: "brand_authority",       label: "Brand Authority",       weight: "20%", manual: true  },
  { key: "content_quality",       label: "Content Quality",       weight: "20%", manual: true  },
  { key: "technical_foundations", label: "Technical Foundations", weight: "10%", manual: false },
  { key: "structured_data",       label: "Structured Data",       weight: "10%", manual: false },
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
  const [overview, actions] = await Promise.all([
    getViewOverview(token),
    getViewActions(token),
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
                    <p className="text-sm font-medium">{dim.label}</p>
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
