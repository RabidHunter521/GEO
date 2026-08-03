// frontend/src/app/view/[token]/progress/page.tsx
// Read-only delivery timeline — published work-log entries only. This is the
// client-safe "what we've done for you" surface (spec §3.5); suggested and
// dismissed entries never reach this page (filtered server-side).
import { notFound } from "next/navigation"
import { ExternalLink, ShieldCheck, Sparkles } from "lucide-react"
import { getViewCompletedWork, getViewWorkLog } from "@/lib/view-api"
import { SectionHeading } from "@/components/view/SectionHeading"
import type { ClientViewWorkLogItem } from "@/types"
import { parseDateOnly } from "@/lib/utils"

export const dynamic = "force-dynamic"

function monthLabel(iso: string): string {
  return parseDateOnly(iso).toLocaleDateString("en-MY", { month: "long", year: "numeric" })
}

export default async function ViewProgressPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [entries, completedWork] = await Promise.all([
    getViewWorkLog(token),
    getViewCompletedWork(token),
  ])
  if (!entries || !completedWork) notFound()

  if (entries.length === 0 && completedWork.length === 0) {
    return (
      <div className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-8 text-center shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles className="h-6 w-6" />
          </span>
          <p className="mt-4 font-display text-lg font-semibold">
            Your first delivery cycle is being prepared
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Reviewed actions will appear here after the SeenBy team completes and
            publishes them.
          </p>
        </div>
      </div>
    )
  }

  const groups = new Map<string, ClientViewWorkLogItem[]>()
  for (const e of entries) {
    const key = monthLabel(e.entry_date)
    groups.set(key, [...(groups.get(key) ?? []), e])
  }

  return (
    <div className="space-y-6">
      <section className="reveal" style={{ animationDelay: "0ms" }}>
        <SectionHeading>Progress</SectionHeading>
        <p className="text-sm text-muted-foreground">
          {entries.length + completedWork.length} improvement
          {entries.length + completedWork.length === 1 ? "" : "s"} delivered.
        </p>
      </section>

      {completedWork.length > 0 && (
        <section className="reveal space-y-4" style={{ animationDelay: "40ms" }}>
          <div>
            <h2 className="font-display text-lg font-semibold">Verified Proof</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Actions checked against follow-up AI visibility scans.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            {completedWork.map((item, idx) => (
              <article
                key={`${item.title}-${idx}`}
                className="card-lift rounded-xl border bg-card p-5"
              >
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-score-strong-bg text-score-strong">
                    <ShieldCheck className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="min-w-[12rem] flex-1 font-display text-sm font-semibold">
                        {item.title}
                      </h3>
                      <span className="rounded-full bg-score-strong-bg px-2.5 py-0.5 text-xs font-medium text-score-strong">
                        {item.status_label}
                      </span>
                    </div>
                    {item.client_safe_summary && (
                      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                        {item.client_safe_summary}
                      </p>
                    )}
                    {item.verification_claim && (
                      <p className="mt-3 rounded-lg border border-score-strong/20 bg-score-strong-bg px-3 py-2 text-xs leading-relaxed text-score-strong">
                        {item.verification_claim}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                      {item.completed_month && <span>Checked {item.completed_month}</span>}
                      {item.destination_url && (
                        <a
                          href={item.destination_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
                        >
                          View destination
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {[...groups.entries()].map(([month, items], i) => (
        <section
          key={month}
          className="reveal card-lift rounded-xl border bg-card p-5"
          style={{ animationDelay: `${80 + i * 30}ms` }}
        >
          <h3 className="font-display text-sm font-semibold">{month}</h3>
          <ul className="mt-3 space-y-3">
            {items.map((e, idx) => (
              <li
                key={`${e.entry_date}-${idx}`}
                className="flex flex-wrap items-start gap-2 border-t pt-3 first:border-t-0 first:pt-0"
              >
                <span className="shrink-0 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
                  {e.category_label}
                </span>
                <span className="min-w-[12rem] flex-1 text-sm text-foreground">
                  {e.description}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {parseDateOnly(e.entry_date).toLocaleDateString("en-MY", {
                    day: "numeric",
                    month: "short",
                  })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
