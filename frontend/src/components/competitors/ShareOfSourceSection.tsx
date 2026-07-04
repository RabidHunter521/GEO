import { ExternalLink } from "lucide-react"
import type { ShareOfSource } from "@/types"

export function ShareOfSourceSection({ data }: { data: ShareOfSource }) {
  if (data.total_third_party_sources === 0) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-display text-lg font-semibold">Sources AI trusts in your category</h3>
        <p className="text-sm text-muted-foreground mt-1">
          No source data yet. Run a scan — SeenBy captures the sources AI leans on to
          answer your category&apos;s questions.
        </p>
      </div>
    )
  }

  const rows: { label: string; pct: number; you: boolean }[] = [
    ...(data.client_share
      ? [{ label: data.client_share.name, pct: data.client_share.share_pct, you: true }]
      : []),
    ...data.competitor_shares.map((c) => ({ label: c.name, pct: c.share_pct, you: false })),
  ]

  return (
    <div className="space-y-6">
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-display text-lg font-semibold">Sources AI trusts in your category</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Of the {data.total_third_party_sources} sources AI leaned on to answer your
          category&apos;s questions, here is who shows up on them.
        </p>
        <div className="mt-4 space-y-3">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center gap-3">
              <span className="w-32 shrink-0 truncate text-sm font-medium">
                {r.label}
                {r.you && <span className="text-muted-foreground"> (you)</span>}
              </span>
              <div className="h-2.5 flex-1 rounded-full bg-muted">
                <div
                  className={`h-2.5 rounded-full ${r.you ? "bg-primary" : "bg-score-watch"}`}
                  style={{ width: `${Math.min(r.pct, 100)}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right text-sm tabular-nums">
                {r.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {data.acquisition_list.length > 0 && (
        <div className="rounded-lg border bg-card p-5">
          <h3 className="font-display text-lg font-semibold">
            Where your competitors are winning attention
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            Sources AI trusts where a competitor appears and you don&apos;t — ranked by how
            often AI relies on them. Earning a mention here is the fastest way to flip the answer.
          </p>
          <div className="mt-4 divide-y">
            {data.acquisition_list.map((s) => (
              <div key={s.url} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm font-medium hover:underline"
                  >
                    <span className="truncate">{s.title ?? s.domain}</span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </a>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {s.domain} · on it: {s.competitors_present.map((c) => c.name).join(", ")}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  seen in {s.citation_count} answers
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
