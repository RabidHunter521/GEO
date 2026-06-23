// frontend/src/app/view/[token]/content-plan/page.tsx
// Read-only content strategy: where the gaps are (the "why"), then the
// 90-day roadmap built from competitor-won queries (the "what's next").
import { Lightbulb } from "lucide-react"
import { getViewContentGaps, getViewRoadmap } from "@/lib/view-api"
import { ClientRoadmapList } from "@/components/view/ClientRoadmapList"

const TOPIC_STATUS: Record<string, { label: string; cls: string }> = {
  strong: { label: "Strong", cls: "bg-score-strong-bg text-score-strong border-score-strong/25" },
  weak: { label: "Needs work", cls: "bg-score-watch-bg text-score-watch border-score-watch/30" },
  missing: { label: "Missing", cls: "bg-score-low-bg text-score-low border-score-low/25" },
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

  // Treat as "has content" only when there's something to render — a gaps
  // object with empty arrays must not slip past and show a bare heading.
  const hasGaps =
    !!gaps &&
    (gaps.topics.length > 0 ||
      gaps.entities.length > 0 ||
      !!gaps.quality_recommendation)
  const hasRoadmap = !!roadmap && roadmap.items.length > 0

  if (!hasGaps && !hasRoadmap) {
    return (
      <div className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-8 text-center shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Lightbulb className="h-6 w-6" />
          </span>
          <p className="mt-4 font-display text-lg font-semibold">
            Your content plan is being built
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Your SeenBy team is analysing your content and competitors to map out
            the topics that will grow your AI visibility. It&apos;ll appear here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Content Gaps — the "why" */}
      {hasGaps && gaps && (
        <section className="reveal space-y-4" style={{ animationDelay: "0ms" }}>
          <div>
            <h2 className="font-display text-lg font-semibold">Where Your Content Stands</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              The topics and details AI looks for when deciding whether to
              recommend you. Gaps here are opportunities.
            </p>
          </div>

          {gaps.topics.length > 0 && (
            <div className="card-lift rounded-xl border bg-card p-5">
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
            <div className="card-lift rounded-xl border bg-card p-5">
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
      {hasRoadmap && roadmap && (
        <section className="reveal space-y-4" style={{ animationDelay: "60ms" }}>
          <div>
            <h2 className="font-display text-lg font-semibold">Your 90-Day Content Plan</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              12 weekly content pieces, built from the questions where your
              competitors are currently winning. Click any title to read the full draft.
            </p>
          </div>

          <ClientRoadmapList items={roadmap.items} />
        </section>
      )}
    </div>
  )
}
