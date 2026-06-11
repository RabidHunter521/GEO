// frontend/src/app/view/[token]/competitors/page.tsx
// Read-only competitor comparison. Language rules: "visibility frequency"
// (never "citation rate") and "Your competitors are winning here"
// (never "visibility gap").
import { notFound } from "next/navigation"
import { TriangleAlert } from "lucide-react"
import { getViewCompetitors } from "@/lib/view-api"
import { VisibilityBadge } from "@/components/view/VisibilityBadge"

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
  const data = await getViewCompetitors(token)
  if (!data) notFound()

  if (data.competitors.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-8 text-center">
        <p className="font-display text-lg font-semibold">
          No competitors tracked yet
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Your SeenBy team will add competitors to compare your AI visibility
          against.
        </p>
      </div>
    )
  }

  const winning = data.competitors.filter((c) => c.is_winning)

  return (
    <div className="space-y-6">
      {/* Your visibility frequency */}
      <div className="rounded-xl border bg-card p-5 shadow-brand">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Your visibility frequency
        </p>
        <p className="mt-1 font-display text-3xl font-semibold tabular-nums">
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
      </div>

      {/* Winning competitors callout */}
      {winning.length > 0 && (
        <div className="rounded-lg border border-score-watch/40 bg-score-watch-bg p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-score-watch">
            <TriangleAlert className="h-4 w-4" />
            Your competitors are winning here
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {winning.map((c) => c.name).join(", ")}{" "}
            {winning.length === 1 ? "is" : "are"} currently seen by AI more
            often than you. The questions below show where.
          </p>
        </div>
      )}

      {/* Per-competitor breakdown */}
      <div className="space-y-3">
        {data.competitors.map((c) => (
          <div key={c.name} className="rounded-lg border bg-card p-4">
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
            {c.queries.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {c.queries.map((q, i) => (
                  <li
                    key={`${c.name}-${i}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="truncate text-muted-foreground">
                      &ldquo;{q.query_text}&rdquo;
                    </span>
                    <VisibilityBadge seen={q.seen_by_ai} className="text-[10px]" />
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
