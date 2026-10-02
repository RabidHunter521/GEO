// frontend/src/app/view/[token]/mirror/page.tsx
// Day-one AI Mirror: what AI assistants say about the client, side by side
// with their top competitor. Linked from the Overview, not a tab. Clients
// only — the API returns the uniform 404 for prospects.
import { notFound } from "next/navigation"
import { getViewMirror } from "@/lib/view-api"
import { AiMirror } from "@/components/mirror/AiMirror"

export default async function ViewMirrorPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const mirror = await getViewMirror(token)
  if (!mirror) notFound()

  return (
    <div className="space-y-6">
      <section className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-6 shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            The AI Mirror
          </p>
          <h1 className="mt-1.5 font-display text-2xl font-semibold">
            What AI says about you
            {mirror.competitor_name ? <>, next to {mirror.competitor_name}</> : null}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            We asked AI assistants about you and about the competitor they favour,
            and quote their answers word for word below. This is where the work starts.
          </p>
        </div>
      </section>
      <section className="reveal" style={{ animationDelay: "60ms" }}>
        <AiMirror mirror={mirror} />
      </section>
    </div>
  )
}
