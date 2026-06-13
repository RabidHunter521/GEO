// frontend/src/app/view/[token]/content-plan/page.tsx
// Read-only content strategy: where the gaps are (the "why"), then the
// 90-day roadmap built from competitor-won queries (the "what's next").
import { Lightbulb, Target } from "lucide-react"
import { getViewContentGaps, getViewRoadmap } from "@/lib/view-api"
import type { ClientViewRoadmapItem } from "@/types"

const TOPIC_STATUS: Record<string, { label: string; cls: string }> = {
  strong: { label: "Strong", cls: "bg-score-strong-bg text-score-strong border-score-strong/25" },
  weak: { label: "Needs work", cls: "bg-score-watch-bg text-score-watch border-score-watch/30" },
  missing: { label: "Missing", cls: "bg-score-low-bg text-score-low border-score-low/25" },
}

const PRIORITY_CLASS: Record<string, string> = {
  high: "bg-score-low-bg text-score-low border-score-low/25",
  medium: "bg-score-watch-bg text-score-watch border-score-watch/30",
  low: "bg-muted text-muted-foreground border-border",
}

export default async function ViewContentPlanPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [gaps, roadmap] = await Promise.all([
    getViewContentGaps(token),
    getViewRoadmap(token),
  ])

  const byMonth = new Map<number, ClientViewRoadmapItem[]>()
  if (roadmap) {
    for (const item of roadmap.items) {
      const arr = byMonth.get(item.month) ?? []
      arr.push(item)
      byMonth.set(item.month, arr)
    }
  }
  const months = [...byMonth.keys()].sort((a, b) => a - b)

  if (!gaps && !roadmap) {
    return (
      <div className="rounded-xl border bg-card p-8 text-center">
        <Lightbulb className="mx-auto h-8 w-8 text-muted-foreground/50" />
        <p className="mt-3 font-display text-lg font-semibold">
          Your content plan is being built
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Your SeenBy team is analysing your content and competitors to map out
          the topics that will grow your AI visibility. It&apos;ll appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Content Gaps — the "why" */}
      {gaps && (
        <section className="space-y-4">
          <div>
            <h2 className="font-display text-lg font-semibold">Where Your Content Stands</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              The topics and details AI looks for when deciding whether to
              recommend you. Gaps here are opportunities.
            </p>
          </div>

          {gaps.topics.length > 0 && (
            <div className="rounded-xl border bg-card p-5">
              <p className="text-sm font-medium">Topic coverage</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {gaps.topics.map((t) => {
                  const meta = TOPIC_STATUS[t.status] ?? TOPIC_STATUS.missing
                  return (
                    <span
                      key={t.topic}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${meta.cls}`}
                    >
                      {t.topic}
                      <span className="opacity-70">· {meta.label}</span>
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {gaps.entities.length > 0 && (
            <div className="rounded-xl border bg-card p-5">
              <p className="text-sm font-medium">Key details AI looks for</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {gaps.entities.map((e) => (
                  <span
                    key={e.entity}
                    className={`rounded-full border px-2.5 py-1 text-xs ${
                      e.covered
                        ? "border-score-strong/25 bg-score-strong-bg text-score-strong"
                        : "bg-muted/40 text-muted-foreground"
                    }`}
                  >
                    {e.covered ? "✓ " : "○ "}
                    {e.entity}
                  </span>
                ))}
              </div>
            </div>
          )}

          {gaps.quality_recommendation && (
            <div className="rounded-xl border bg-primary/5 p-5">
              <p className="flex items-center gap-2 text-sm font-medium">
                <Lightbulb className="h-4 w-4 text-primary" />
                Our recommendation
              </p>
              <p className="mt-1.5 text-sm leading-relaxed text-foreground">
                {gaps.quality_recommendation}
              </p>
            </div>
          )}
        </section>
      )}

      {/* 90-day Roadmap — the "what's next" */}
      {roadmap && roadmap.items.length > 0 && (
        <section className="space-y-4">
          <div>
            <h2 className="font-display text-lg font-semibold">Your 90-Day Content Plan</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Built from the questions where your competitors are currently
              winning. Each piece is chosen to win back AI visibility.
            </p>
          </div>

          {months.map((month) => (
            <div key={month}>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Month {month}
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {byMonth.get(month)!.map((item, i) => (
                  <div key={`${month}-${i}`} className="rounded-lg border bg-card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          {item.theme}
                        </p>
                        <p className="mt-1 font-medium leading-snug">{item.suggested_title}</p>
                      </div>
                      <span
                        className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                          PRIORITY_CLASS[item.priority] ?? PRIORITY_CLASS.low
                        }`}
                      >
                        {item.priority}
                      </span>
                    </div>
                    {item.content_type && (
                      <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground">
                        {item.content_type}
                      </p>
                    )}
                    {item.rationale && (
                      <p className="mt-2 text-sm text-muted-foreground">{item.rationale}</p>
                    )}
                    {item.target_queries.length > 0 && (
                      <div className="mt-3 border-t pt-2.5">
                        <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
                          <Target className="h-3 w-3" />
                          Wins back these questions
                        </p>
                        <ul className="mt-1.5 space-y-1">
                          {item.target_queries.slice(0, 3).map((q) => (
                            <li key={q} className="text-xs text-muted-foreground">
                              &ldquo;{q}&rdquo;
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
