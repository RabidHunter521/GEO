// frontend/src/app/view/[token]/scan/page.tsx
// Read-only scan results: what AI was asked, whether the client was seen, and a
// curated, competitor-redacted excerpt of the answer. Raw AI responses are
// never available on this surface.
import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowRight, Radar } from "lucide-react"
import { getViewScan, getViewOverview } from "@/lib/view-api"
import { VisibilityBadge } from "@/components/view/VisibilityBadge"
import { PlatformIcon } from "@/components/view/PlatformIcon"
import { SectionHeading } from "@/components/view/SectionHeading"
import { segmentQueries } from "@/lib/query-segments"
import type { ClientViewScanResult } from "@/types"

const CATEGORY_LABEL: Record<string, string> = {
  brand: "Questions about your brand",
  comparison: "You vs competitors",
  recommendation: "Best-in-industry questions",
  local: "Local search questions",
}

// First rows shown per segment before the reader has to open "Show all".
const PREVIEW_COUNT = 5

// Compact single-line preview used above the full per-category tables — the
// tables below remain the complete, unfiltered evidence.
function QueryPreviewRow({ result }: { result: ClientViewScanResult }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2 text-sm">
      <span className="flex min-w-0 items-center gap-2">
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-muted/30 px-2 py-0.5 text-[10px] font-medium">
          <PlatformIcon label={result.platform_label} className="h-3 w-3" />
          {result.platform_label}
        </span>
        <span className="truncate text-muted-foreground">&ldquo;{result.query_text}&rdquo;</span>
      </span>
      <VisibilityBadge seen={result.seen_by_ai} className="shrink-0 text-[10px]" />
    </div>
  )
}

function SegmentPreview({
  label,
  results,
}: {
  label: string
  results: ClientViewScanResult[]
}) {
  if (results.length === 0) return null
  const preview = results.slice(0, PREVIEW_COUNT)
  const rest = results.slice(PREVIEW_COUNT)
  return (
    <div className="mt-3 first:mt-0">
      <p className="text-xs font-semibold text-muted-foreground">
        {label} ({results.length})
      </p>
      <div className="mt-2 space-y-2">
        {preview.map((r, i) => (
          <QueryPreviewRow key={`${label}-${i}`} result={r} />
        ))}
      </div>
      {rest.length > 0 && (
        <details className="mt-2">
          <summary className="list-none marker:hidden cursor-pointer text-xs font-medium text-primary hover:underline">
            Show all {results.length}
          </summary>
          <div className="mt-2 space-y-2">
            {rest.map((r, i) => (
              <QueryPreviewRow key={`${label}-more-${i}`} result={r} />
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

export default async function ViewScanPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [scan, overview] = await Promise.all([getViewScan(token), getViewOverview(token)])
  if (!scan) notFound()
  const isProspect = overview?.profile.is_prospect ?? true

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
  const segments = segmentQueries(scan.results, (r) => ({ seen: r.seen_by_ai }))

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
          {!isProspect && (
            <Link
              href={`/view/${token}/competitors`}
              className="mt-3 inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
            >
              See how you compare to competitors
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>
      </section>

      <section
        className="reveal rounded-xl border bg-card p-4"
        style={{ animationDelay: "30ms" }}
      >
        <SectionHeading>Evidence summary</SectionHeading>
        <div className="flex flex-wrap gap-2 text-xs">
          {segments.newlySeen.length > 0 && (
            <span className="rounded-full border border-score-strong/30 bg-score-strong-bg px-2.5 py-1 font-medium text-score-strong">
              {segments.newlySeen.length} newly seen by AI this scan
            </span>
          )}
          {segments.newlyLost.length > 0 && (
            <span className="rounded-full border border-score-watch/30 bg-score-watch-bg px-2.5 py-1 font-medium text-score-watch">
              {segments.newlyLost.length} newly lost since last scan
            </span>
          )}
          <span className="rounded-full border bg-muted/30 px-2.5 py-1 font-medium text-muted-foreground">
            {segments.opportunities.length} not yet seen by AI
          </span>
          <span className="rounded-full border bg-muted/30 px-2.5 py-1 font-medium text-muted-foreground">
            {segments.other.length} already seen by AI
          </span>
        </div>
        <SegmentPreview label="Newly seen by AI this scan" results={segments.newlySeen} />
        <SegmentPreview label="Newly lost since last scan" results={segments.newlyLost} />
        <SegmentPreview label="Not yet seen by AI" results={segments.opportunities} />
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
