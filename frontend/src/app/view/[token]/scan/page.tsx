// frontend/src/app/view/[token]/scan/page.tsx
// Read-only scan results: what AI was asked, whether the client was seen, and a
// curated, competitor-redacted excerpt of the answer. Raw AI responses are
// never available on this surface.
import { notFound } from "next/navigation"
import { getViewScan } from "@/lib/view-api"
import { VisibilityBadge } from "@/components/view/VisibilityBadge"
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
      <div className="rounded-xl border bg-card p-8 text-center">
        <p className="font-display text-lg font-semibold">
          Your first AI visibility scan is being prepared
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          The SeenBy team will run your scan shortly. Results will appear here.
        </p>
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
      <div className="rounded-xl border bg-card p-5 shadow-brand">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Latest Scan
        </p>
        <p className="mt-1 font-display text-2xl font-semibold">
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

      {Object.entries(grouped).map(([category, results]) => (
        <div key={category}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {CATEGORY_LABEL[category] ?? category}
          </h2>
          <div className="space-y-2">
            {results.map((r, i) => (
              <div
                key={`${category}-${i}`}
                className="flex flex-col gap-2 rounded-lg border bg-card p-4"
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <span className="shrink-0 rounded-full border bg-muted/30 px-2.5 py-0.5 text-xs font-medium">
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
                  <details className="mt-1 w-full">
                    <summary className="cursor-pointer text-xs font-medium text-primary hover:underline">
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
        </div>
      ))}
    </div>
  )
}
