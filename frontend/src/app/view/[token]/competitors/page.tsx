// frontend/src/app/view/[token]/competitors/page.tsx
// Read-only competitor comparison. Language rules: "visibility frequency"
// (never "citation rate") and "Your competitors are winning here"
// (never "visibility gap").
import { notFound } from "next/navigation"
import { TriangleAlert, Users } from "lucide-react"
import { getViewCompetitors, getViewCompetitorTrends } from "@/lib/view-api"
import { VisibilityBadge } from "@/components/view/VisibilityBadge"
import { PlatformIcon } from "@/components/view/PlatformIcon"
import { VisibilityTrendChart } from "@/components/competitors/VisibilityTrendChart"

function FrequencyBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export default async function ViewCompetitorsPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [data, trends] = await Promise.all([
    getViewCompetitors(token),
    getViewCompetitorTrends(token).catch(() => null),
  ])
  if (!data) notFound()

  if (data.competitors.length === 0) {
    return (
      <div className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-8 text-center shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Users className="h-6 w-6" />
          </span>
          <p className="mt-4 font-display text-lg font-semibold">
            No competitors tracked yet
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Your SeenBy team will add competitors to compare your AI visibility
            against.
          </p>
        </div>
      </div>
    )
  }

  const winning = data.competitors.filter((c) => c.is_winning)

  return (
    <div className="space-y-6">
      {/* Your visibility frequency */}
      <section
        className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-6 shadow-brand-lg"
        style={{ animationDelay: "0ms" }}
      >
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Your visibility frequency
          </p>
          <p className="mt-1.5 font-display text-3xl font-semibold tabular-nums">
            {data.your_visibility_frequency !== null
              ? `${data.your_visibility_frequency.toFixed(0)}%`
              : "—"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            How often you were seen by AI across the questions we asked
            {data.last_scan_at && (
              <>
                {" "}
                — last checked{" "}
                {new Date(data.last_scan_at).toLocaleDateString("en-MY", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </>
            )}
            .
          </p>
          {Object.keys(data.your_platform_visibility).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
              {Object.entries(data.your_platform_visibility).map(([label, value]) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1.5 rounded-full border bg-muted/30 px-2.5 py-1 text-xs tabular-nums"
                >
                  <PlatformIcon label={label} className="h-3.5 w-3.5" />
                  {label}: <span className="font-semibold">{value.toFixed(0)}%</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Visibility trend over time */}
      {trends && trends.checked_at.length >= 2 && (
        <section className="reveal" style={{ animationDelay: "60ms" }}>
          <VisibilityTrendChart
            dates={trends.checked_at}
            series={trends.series.map((s) => ({
              name: s.name,
              isYou: s.is_you,
              points: s.points,
            }))}
            heading="Your visibility frequency over time"
          />
        </section>
      )}

      {/* Winning competitors callout */}
      {winning.length > 0 && (
        <section
          className="reveal rounded-xl border border-score-watch/40 bg-score-watch-bg p-4"
          style={{ animationDelay: "90ms" }}
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-score-watch">
            <TriangleAlert className="h-4 w-4" />
            Your competitors are winning here
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {winning.map((c) => c.name).join(", ")}{" "}
            {winning.length === 1 ? "is" : "are"} currently seen by AI more
            often than you. The questions below show where.
          </p>
        </section>
      )}

      {/* The battle to win next */}
      {data.headline_battle && (
        <section
          className="reveal rounded-xl border border-score-watch/40 bg-score-watch-bg p-4"
          style={{ animationDelay: "105ms" }}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-score-watch">
            The battle to win next
          </p>
          <p className="mt-2 text-sm text-foreground">
            Your competitor{" "}
            <span className="font-semibold">{data.headline_battle.rival_name}</span>{" "}
            is winning &ldquo;{data.headline_battle.query_text}&rdquo; on{" "}
            {data.headline_battle.platform_label}.
          </p>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {data.headline_battle.move_title ? (
              <>
                The one move to flip it:{" "}
                <span className="font-medium text-foreground">
                  {data.headline_battle.move_title}
                </span>
                {data.headline_battle.move_angle && (
                  <> — {data.headline_battle.move_angle}</>
                )}
              </>
            ) : (
              <>The play to flip it is being prepared.</>
            )}
          </p>
        </section>
      )}

      {/* Per-competitor breakdown */}
      <section className="reveal space-y-3" style={{ animationDelay: "120ms" }}>
        {data.competitors.map((c) => (
          <div key={c.name} className="card-lift rounded-xl border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{c.name}</p>
                {c.website && (
                  <p className="truncate text-xs text-muted-foreground">
                    {c.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                  </p>
                )}
              </div>
              <div className="shrink-0 text-right">
                <p className="font-display text-lg font-semibold tabular-nums">
                  {c.visibility_frequency.toFixed(0)}%
                </p>
                <p className="text-xs text-muted-foreground">
                  visibility frequency
                </p>
              </div>
            </div>
            <div className="mt-3">
              <FrequencyBar value={c.visibility_frequency} />
            </div>
            {c.takeaway && (
              <p className="mt-3 text-sm font-medium text-foreground">
                {c.takeaway}
              </p>
            )}
            {c.winning_platform_labels.length > 0 && (
              <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-score-watch">
                <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                Your competitors are winning here:{" "}
                {c.winning_platform_labels.join(", ")}
              </p>
            )}
            {c.queries.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {c.queries.map((q, i) => (
                  <li
                    key={`${c.name}-${i}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-muted/30 px-2 py-0.5 text-[10px] font-medium">
                        <PlatformIcon label={q.platform_label} className="h-3 w-3" />
                        {q.platform_label}
                      </span>
                      <span className="truncate text-muted-foreground">
                        &ldquo;{q.query_text}&rdquo;
                      </span>
                    </span>
                    <VisibilityBadge seen={q.seen_by_ai} className="text-[10px]" />
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </section>
    </div>
  )
}
