// frontend/src/app/view/[token]/scan/page.tsx
// Read-only scan results: what AI was asked, whether the client was seen, and a
// curated, competitor-redacted excerpt of the answer. Raw AI responses are
// never available on this surface.
import { notFound } from "next/navigation"
import { Radar } from "lucide-react"
import { getViewScan } from "@/lib/view-api"
import { VisibilityBadge } from "@/components/view/VisibilityBadge"
import { PlatformIcon } from "@/components/view/PlatformIcon"
import { SectionHeading } from "@/components/view/SectionHeading"
import type { ClientViewScanResult } from "@/types"

const CATEGORY_LABEL: Record<string, string> = {
  brand: "Questions about your brand",
  comparison: "You vs competitors",
  recommendation: "Best-in-industry questions",
  local: "Local search questions",
}

export default async function ViewScanPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const scan = await getViewScan(token)
  if (!scan) notFound()

  if (scan.results.length === 0) {
    return (
      <div className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-8 text-center shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Radar className="h-6 w-6" />
          </span>
          <p className="mt-4 font-display text-lg font-semibold">
            Your first AI visibility scan is being prepared
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            The SeenBy team will run your scan shortly. Results will appear here.
          </p>
        </div>
      </div>
    )
  }

  const grouped = scan.results.reduce<Record<string, ClientViewScanResult[]>>(
    (acc, r) => {
      ;(acc[r.category] ??= []).push(r)
      return acc
    },
    {},
  )

  const seenCount = scan.results.filter((r) => r.seen_by_ai).length

  return (
    <div className="space-y-6">
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
            Latest Scan
          </p>
          <p className="mt-1.5 font-display text-2xl font-semibold">
            Seen by AI in {seenCount} of {scan.results.length} questions
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            We asked AI platforms the questions your customers ask
            {scan.completed_at && (
              <>
                {" "}
                — last checked{" "}
                {new Date(scan.completed_at).toLocaleDateString("en-MY", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </>
            )}
            .
          </p>
        </div>
      </section>

      {Object.entries(grouped).map(([category, results], gi) => (
        <section
          key={category}
          className="reveal"
          style={{ animationDelay: `${Math.min(60 + gi * 60, 300)}ms` }}
        >
          <SectionHeading>{CATEGORY_LABEL[category] ?? category}</SectionHeading>
          <div className="space-y-2">
            {results.map((r, i) => (
              <div
                key={`${category}-${i}`}
                className="card-lift flex flex-col gap-2 rounded-xl border bg-card p-4"
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-muted/30 px-2.5 py-0.5 text-xs font-medium">
                      <PlatformIcon label={r.platform_label} className="h-3.5 w-3.5" />
                      {r.platform_label}
                    </span>
                    <p className="text-sm">&ldquo;{r.query_text}&rdquo;</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {r.seen_by_ai && r.ai_search_ranking !== null && (
                      <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                        AI Search Ranking #{r.ai_search_ranking}
                      </span>
                    )}
                    <VisibilityBadge seen={r.seen_by_ai} />
                  </div>
                </div>
                {r.excerpt && (
                  <details className="mt-1 w-full" aria-label="AI answer excerpt">
                    <summary className="list-none marker:hidden cursor-pointer text-xs font-medium text-primary hover:underline">
                      See what AI said
                    </summary>
                    <blockquote className="mt-2 border-l-2 border-muted pl-3 text-sm italic leading-relaxed text-muted-foreground">
                      &ldquo;{r.excerpt}&rdquo;
                    </blockquote>
                  </details>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
