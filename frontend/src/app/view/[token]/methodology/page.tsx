// frontend/src/app/view/[token]/methodology/page.tsx
// How the score is built, published for the client to check.
//
// Not a primary tab (CLAUDE.md §9 fixes ViewTabs at six destinations) — reached
// from the score tile on the Overview, the same way /competitors is reached.
//
// Every number on this page comes from the /methodology endpoint, which derives
// them from backend constants. Nothing here is retyped, so a weight change
// cannot leave a stale published methodology behind.
import { notFound } from "next/navigation"
import Link from "next/link"
import { ArrowLeft, CircleCheck, UserCheck } from "lucide-react"
import { getViewMethodology } from "@/lib/view-api"

export default async function ViewMethodologyPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const m = await getViewMethodology(token)
  if (!m) notFound()

  const measured = m.dimensions.filter((d) => d.basis === "measured")
  const reviewed = m.dimensions.filter((d) => d.basis === "reviewed")

  return (
    <div className="space-y-8">
      <section className="reveal space-y-3" style={{ animationDelay: "0ms" }}>
        <Link
          href={`/view/${token}`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to overview
        </Link>
        <h2 className="font-display text-xl font-semibold">
          How your {m.score_label} score is measured
        </h2>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Your {m.score_label} score combines five parts. Some are checked
          automatically; others are researched from public evidence and signed
          off by a person before they count. Both are shown below, with exactly
          how much each one contributes.
        </p>
      </section>

      <section className="reveal space-y-4" style={{ animationDelay: "60ms" }}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border bg-card p-4">
            <div className="flex items-center gap-2 text-primary">
              <CircleCheck className="h-4 w-4" />
              <p className="text-sm font-medium">Checked automatically</p>
            </div>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {m.measured_weight_percent}%
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              of your score, from AI answers and live checks of your own site
            </p>
          </div>
          <div className="rounded-xl border bg-card p-4">
            <div className="flex items-center gap-2 text-primary">
              <UserCheck className="h-4 w-4" />
              <p className="text-sm font-medium">Reviewed by a person</p>
            </div>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {m.reviewed_weight_percent}%
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              of your score, researched from public evidence and signed off
            </p>
          </div>
        </div>
      </section>

      <section className="reveal space-y-4" style={{ animationDelay: "120ms" }}>
        <h3 className="font-display text-lg font-semibold">What makes up the score</h3>
        <div className="space-y-3">
          {[...measured, ...reviewed].map((d) => (
            <div key={d.key} className="rounded-xl border bg-card p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-medium">{d.label}</p>
                <p className="text-sm font-semibold tabular-nums text-muted-foreground">
                  {d.weight_percent}% of your score
                </p>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{d.description}</p>
              {d.evidence_label && (
                <p className="mt-2 text-xs italic text-muted-foreground">
                  {d.evidence_label}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      {m.platforms.length > 0 && (
        <section className="reveal space-y-3" style={{ animationDelay: "180ms" }}>
          <h3 className="font-display text-lg font-semibold">Where we check</h3>
          <p className="text-sm text-muted-foreground">
            We ask your tracked buyer questions on {m.platforms.join(", ")}.
          </p>
        </section>
      )}

      <section className="reveal space-y-3" style={{ animationDelay: "240ms" }}>
        <h3 className="font-display text-lg font-semibold">
          When we improve the method
        </h3>
        <p className="max-w-2xl text-sm text-muted-foreground">{m.version_policy}</p>
      </section>

      <section className="reveal space-y-3" style={{ animationDelay: "300ms" }}>
        <h3 className="font-display text-lg font-semibold">What this score does not tell you</h3>
        <ul className="space-y-2">
          {m.limitations.map((line) => (
            <li key={line} className="flex gap-2 text-sm text-muted-foreground">
              <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </section>

      <p className="text-xs text-muted-foreground">
        Method version {m.score_version}
      </p>
    </div>
  )
}
