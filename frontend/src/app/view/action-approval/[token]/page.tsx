import type { Metadata } from "next"
import { redirect } from "next/navigation"
import { CheckCircle2, ExternalLink, MessageSquareText, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LinkInactive } from "@/components/view/LinkInactive"

export const dynamic = "force-dynamic"

export const metadata: Metadata = {
  title: "Action approval - SeenBy",
  robots: { index: false, follow: false },
}

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

type ApprovalPayload = {
  business_name: string
  action_title: string
  client_safe_summary: string | null
  deliverable_url: string | null
  destination_url: string | null
  expires_at: string
}

async function getApproval(token: string): Promise<ApprovalPayload | null> {
  const res = await fetch(`${BASE}/api/v1/action-approvals/${encodeURIComponent(token)}`, {
    cache: "no-store",
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`Approval API GET failed with ${res.status}`)
  return res.json() as Promise<ApprovalPayload>
}

async function submitDecision(
  token: string,
  decision: "approve" | "request_changes",
  formData: FormData,
) {
  "use server"
  if (formData.get("confirm") !== "on") {
    redirect(`/view/action-approval/${encodeURIComponent(token)}?error=confirm`)
  }
  const rawComment = formData.get("comment")
  const comment = typeof rawComment === "string" && rawComment.trim() ? rawComment.trim() : null
  if (comment && comment.length > 2000) {
    redirect(`/view/action-approval/${encodeURIComponent(token)}?error=comment`)
  }

  const res = await fetch(`${BASE}/api/v1/action-approvals/${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, comment }),
    cache: "no-store",
  })
  if (res.status === 404) {
    redirect(`/view/action-approval/${encodeURIComponent(token)}?inactive=1`)
  }
  if (!res.ok) {
    redirect(`/view/action-approval/${encodeURIComponent(token)}?error=submit`)
  }
  redirect(`/view/action-approval/${encodeURIComponent(token)}?decided=${decision}`)
}

function formatExpiry(value: string) {
  return new Date(value).toLocaleString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

function Confirmation({ decision }: { decision: string }) {
  const approved = decision === "approve"
  return (
    <main className="flex min-h-screen items-center justify-center bg-app-wash px-4 py-10">
      <section className="w-full max-w-lg rounded-xl border bg-card p-8 text-center shadow-brand">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-score-strong-bg text-score-strong">
          <CheckCircle2 className="h-6 w-6" />
        </span>
        <p className="mt-4 font-display text-lg font-bold tracking-tight text-primary">
          SeenBy
        </p>
        <h1 className="mt-3 font-display text-2xl font-semibold">
          {approved ? "Approval recorded" : "Change request recorded"}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Thanks. Your SeenBy team has received this decision and will continue from here.
        </p>
      </section>
    </main>
  )
}

export default async function ActionApprovalPage({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>
  searchParams?: Promise<{ decided?: string; error?: string; inactive?: string }>
}) {
  const { token } = await params
  const query = searchParams ? await searchParams : {}
  if (query.decided === "approve" || query.decided === "request_changes") {
    return <Confirmation decision={query.decided} />
  }
  if (query.inactive) {
    return <LinkInactive />
  }

  const approval = await getApproval(token)
  if (!approval) {
    return <LinkInactive />
  }

  const approveAction = submitDecision.bind(null, token, "approve")
  const requestChangesAction = submitDecision.bind(null, token, "request_changes")
  const links = [
    approval.deliverable_url ? { label: "Review deliverable", href: approval.deliverable_url } : null,
    approval.destination_url ? { label: "Review destination", href: approval.destination_url } : null,
  ].filter((link): link is { label: string; href: string } => Boolean(link))

  return (
    <main className="min-h-screen bg-app-wash px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-3xl space-y-5">
        <header className="rounded-xl border bg-card p-6 shadow-brand sm:p-8">
          <p className="font-display text-lg font-bold tracking-tight text-primary">
            SeenBy
          </p>
          <div className="mt-5 flex items-start gap-3">
            <span className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <ShieldCheck className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium text-muted-foreground">
                {approval.business_name}
              </p>
              <h1 className="mt-1 text-balance font-display text-2xl font-semibold leading-tight text-foreground sm:text-3xl">
                {approval.action_title}
              </h1>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {approval.client_safe_summary ?? "Your SeenBy team has prepared this action for review."}
              </p>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
            <span className="rounded-full bg-secondary px-3 py-1 text-secondary-foreground">
              Expires {formatExpiry(approval.expires_at)}
            </span>
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 font-medium text-primary hover:bg-primary/15"
              >
                {link.label}
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            ))}
          </div>
        </header>

        {query.error && (
          <p className="rounded-md border border-score-low/25 bg-score-low-bg px-4 py-3 text-sm text-score-low">
            We could not record that decision. Please check the confirmation box and try again.
          </p>
        )}

        <section className="grid gap-4 md:grid-cols-2">
          <form action={approveAction} className="rounded-xl border bg-card p-5 shadow-brand">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-score-strong" />
              <h2 className="font-display text-lg font-semibold">Approve</h2>
            </div>
            <label htmlFor="approve-comment" className="mt-4 block text-sm font-medium">
              Optional comment
            </label>
            <textarea
              id="approve-comment"
              name="comment"
              maxLength={2000}
              rows={4}
              className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              placeholder="Anything the team should know before publishing?"
            />
            <label className="mt-4 flex items-start gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                name="confirm"
                required
                className="mt-1 h-4 w-4 rounded border-input"
              />
              <span>I confirm this action is approved for the SeenBy team to proceed.</span>
            </label>
            <Button type="submit" className="mt-4 w-full">
              <CheckCircle2 className="h-4 w-4" />
              Approve action
            </Button>
          </form>

          <form action={requestChangesAction} className="rounded-xl border bg-card p-5 shadow-brand">
            <div className="flex items-center gap-2">
              <MessageSquareText className="h-5 w-5 text-primary" />
              <h2 className="font-display text-lg font-semibold">Request changes</h2>
            </div>
            <label htmlFor="changes-comment" className="mt-4 block text-sm font-medium">
              Comment
            </label>
            <textarea
              id="changes-comment"
              name="comment"
              maxLength={2000}
              rows={4}
              className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              placeholder="Tell us what needs to change."
            />
            <label className="mt-4 flex items-start gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                name="confirm"
                required
                className="mt-1 h-4 w-4 rounded border-input"
              />
              <span>I confirm this should go back to the SeenBy team for changes.</span>
            </label>
            <Button type="submit" variant="outline" className="mt-4 w-full">
              <MessageSquareText className="h-4 w-4" />
              Send request
            </Button>
          </form>
        </section>
      </div>
    </main>
  )
}
