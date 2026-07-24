// frontend/src/app/view/[token]/progress/page.tsx
// Read-only delivery timeline — published work-log entries only. This is the
// client-safe "what we've done for you" surface (spec §3.5); suggested and
// dismissed entries never reach this page (filtered server-side).
import { Sparkles } from "lucide-react"
import { getViewWorkLog } from "@/lib/view-api"
import { SectionHeading } from "@/components/view/SectionHeading"
import type { ClientViewWorkLogItem } from "@/types"

export const dynamic = "force-dynamic"

function monthLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-MY", { month: "long", year: "numeric" })
}

export default async function ViewProgressPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const entries = (await getViewWorkLog(token)) ?? []

  if (entries.length === 0) {
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
          <p className="mt-4 font-display text-lg font-semibold">Progress</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Your delivery timeline will appear here as work is completed.
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
          {entries.length} improvement{entries.length === 1 ? "" : "s"} delivered.
        </p>
      </section>

      {[...groups.entries()].map(([month, items], i) => (
        <section
          key={month}
          className="reveal card-lift rounded-xl border bg-card p-5"
          style={{ animationDelay: `${60 + i * 30}ms` }}
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
                  {new Date(e.entry_date).toLocaleDateString("en-MY", {
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
