// frontend/src/app/view/[token]/reputation/page.tsx
// Read-only reputation surface, built from exactly two whitelisted endpoints:
// - /progress, filtered to "hallucination" items only — reviewed AI-accuracy
//   issues and what's been corrected. "content_gap" items (competitors
//   winning a query) live on the Action Plan instead, not here.
// - /issues, filtered to the brand_authority / technical_foundations /
//   structured_data dimensions — ai_visibility lives on Visibility and
//   content_quality lives on the Action Plan, so repeating them here would
//   duplicate another tab.
// Never fetches activity — ActivityLog uses internal admin vocabulary and is
// admin-only by construction (CLAUDE.md §9).
import { notFound } from "next/navigation"
import { CheckCircle2, ShieldCheck } from "lucide-react"
import { getViewIssues, getViewProgress, getViewTruthHealth } from "@/lib/view-api"
import { ClientProgressList } from "@/components/view/ClientProgressList"
import { PRODUCT_LANGUAGE } from "@/lib/product-language"
import type { ClientViewIssueGroup } from "@/types"

const REPUTATION_DIMENSIONS = new Set<ClientViewIssueGroup["dimension"]>([
  "brand_authority",
  "technical_foundations",
  "structured_data",
])

export default async function ViewReputationPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [issues, progress, truthHealth] = await Promise.all([
    getViewIssues(token),
    getViewProgress(token),
    getViewTruthHealth(token),
  ])
  if (!issues || !progress || !truthHealth) notFound()

  const accuracyItems = progress.filter((p) => p.item_type === "hallucination")
  const reputationIssues = issues.filter((g) => REPUTATION_DIMENSIONS.has(g.dimension))

  const hasAccuracy = accuracyItems.length > 0
  const hasIssues = reputationIssues.length > 0
  const hasTruth = truthHealth.locations.length > 0
    || truthHealth.reviewed_open_issue_count > 0
    || truthHealth.corrected_count > 0

  // Honesty over completeness (Phase 0's governing rule): with nothing
  // reviewed yet, say so plainly rather than rendering an empty module that
  // reads as "work happened here."
  if (!hasAccuracy && !hasIssues && !hasTruth) {
    return (
      <div className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-8 text-center shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <ShieldCheck className="h-6 w-6" />
          </span>
          <p className="mt-4 font-display text-lg font-semibold">
            No reputation issues flagged yet
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Your SeenBy team reviews AI answers for accuracy and checks your
            brand authority and technical foundations. Anything found will
            appear here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <section className="reveal space-y-4" style={{ animationDelay: "0ms" }}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-semibold">Accuracy Health</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              A summary based only on business information verified by your SeenBy team.
            </p>
          </div>
          {truthHealth.fact_freshness && (
            <p className="text-xs text-muted-foreground">
              Information last verified {new Date(truthHealth.fact_freshness).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </p>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border bg-card p-4">
            <p className="text-2xl font-semibold tabular-nums">
              {truthHealth.reviewed_open_issue_count}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {truthHealth.reviewed_open_issue_count === 1 ? "reviewed issue open" : "reviewed issues open"}
            </p>
          </div>
          <div className="rounded-xl border bg-card p-4">
            <p className="text-2xl font-semibold tabular-nums">{truthHealth.corrected_count}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {truthHealth.corrected_count === 1
                ? "corrective action awaiting proof"
                : "corrective actions awaiting proof"}
            </p>
          </div>
        </div>

        {truthHealth.open_issues.length > 0 && (
          <div className="rounded-xl border bg-card p-4">
            <h3 className="font-medium">Open reviewed issues</h3>
            <ul className="mt-2 space-y-2 text-sm text-muted-foreground">
              {truthHealth.open_issues.map((issue, index) => (
                <li key={`${issue.status_label}-${index}`} className="flex gap-2">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>{issue.summary}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {truthHealth.resolved_issues.length > 0 && (
          <div className="rounded-xl border bg-card p-4">
            <h3 className="font-medium">Resolved issues</h3>
            <ul className="mt-2 space-y-2 text-sm text-muted-foreground">
              {truthHealth.resolved_issues.map((issue, index) => (
                <li key={`${issue.status_label}-${index}`} className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-score-strong" />
                  <span>{issue.summary} {issue.status_label}.</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="reveal space-y-4" style={{ animationDelay: "30ms" }}>
        <div>
          <h2 className="font-display text-lg font-semibold">Verified business information</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Current details that have been approved for your active locations.
          </p>
        </div>
        {truthHealth.locations.length > 1 && (
          <nav aria-label="Location selector" className="flex flex-wrap gap-2">
            {truthHealth.locations.map((location, index) => (
              <a
                key={`${location.name}-${index}`}
                href={`#location-${index + 1}`}
                className="rounded-full border px-3 py-1 text-sm font-medium hover:bg-muted"
              >
                {location.name}
              </a>
            ))}
          </nav>
        )}
        {truthHealth.locations.length === 0 ? (
          <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
            No active business locations have been verified yet.
          </p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {truthHealth.locations.map((location, index) => (
              <article id={`location-${index + 1}`} key={`${location.name}-${index}`} className="rounded-xl border bg-card p-4">
                <h3 className="font-medium">{location.name}</h3>
                {location.city && <p className="mt-1 text-sm text-muted-foreground">{location.city}</p>}
                {location.hours_summary && (
                  <p className="mt-3 text-sm text-muted-foreground">{location.hours_summary}</p>
                )}
                {location.service_categories.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2" aria-label="Verified service categories">
                    {location.service_categories.map((category) => (
                      <span key={category} className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                        {category}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      {hasAccuracy && (
        <section className="reveal space-y-3" style={{ animationDelay: "60ms" }}>
          <div>
            <h2 className="font-display text-lg font-semibold">
              {PRODUCT_LANGUAGE.accuracy}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              AI answers your SeenBy team has reviewed for accuracy, and where
              each one stands.
            </p>
          </div>
          <ClientProgressList items={accuracyItems} />
        </section>
      )}

      {hasIssues && (
        <section className="reveal space-y-4" style={{ animationDelay: "90ms" }}>
          <div>
            <h2 className="font-display text-lg font-semibold">
              Brand Authority &amp; Technical Foundations
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              What&apos;s shaping how AI and search engines read your
              brand&apos;s credibility and technical readiness.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {reputationIssues.map((group) => (
              <div key={group.dimension} className="card-lift rounded-xl border bg-card p-4">
                <p className="text-sm font-medium">
                  {group.dimension_label}
                  {group.dimension === "brand_authority" && (
                    <span className="ml-1.5 text-xs font-normal italic text-muted-foreground">
                      · Based on public evidence · Reviewed by SeenBy
                    </span>
                  )}
                </p>
                <ul className="ml-4 mt-2 list-disc space-y-1 text-sm text-muted-foreground">
                  {group.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
