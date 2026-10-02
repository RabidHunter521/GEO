"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { PLACEMENT_CATEGORY_LABEL, PLACEMENT_STATUS_LABEL, mailtoHref } from "@/lib/placements"
import { PLATFORM_LABELS } from "@/types"
import type { PlacementDraft, PlacementEmailDraft, PlacementTargetDetail } from "@/types"
import {
  analyzePlacementAction, createPlacementDraftAction, editPlacementDraftAction, getPlacementAction,
  pursuePlacementAction, setPlacementStatusAction, type PlacementResult,
} from "@/app/(admin)/clients/[id]/authority/placement-actions"

export function PlacementDetailDialog({
  clientId, targetId, onOpenChange, onUpdated,
}: {
  clientId: string
  targetId: string | null
  onOpenChange: (open: boolean) => void
  onUpdated: (t: PlacementTargetDetail) => void
}) {
  const [detail, setDetail] = useState<PlacementTargetDetail | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dueDate, setDueDate] = useState("")

  useEffect(() => {
    setDetail(null)
    setError(null)
    if (!targetId) return
    let live = true
    getPlacementAction(clientId, targetId).then((r) => {
      if (!live) return
      if (r.ok) setDetail(r.detail)
      else setError(r.error)
    })
    return () => { live = false }
  }, [clientId, targetId])

  async function act(label: string, fn: () => Promise<PlacementResult>) {
    setBusy(label)
    setError(null)
    try {
      const r = await fn()
      if (r.ok) {
        setDetail(r.detail)
        onUpdated(r.detail)
      } else {
        setError(r.error)
      }
    } finally {
      setBusy(null)
    }
  }

  const t = detail
  const analysis = t?.page_analysis
  const canPursue = t && (t.status === "open" || t.status === "stale")

  return (
    <Dialog open={targetId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        {!t ? (
          <DialogHeader>
            <DialogTitle>Placement</DialogTitle>
            <DialogDescription>{error ?? "Loading…"}</DialogDescription>
          </DialogHeader>
        ) : (
          <div className="space-y-5">
            <DialogHeader>
              <DialogTitle className="pr-6">{t.title ?? t.domain}</DialogTitle>
              <DialogDescription>
                <a href={t.url} target="_blank" rel="noopener noreferrer" className="underline">{t.url}</a>
              </DialogDescription>
              <div className="flex flex-wrap gap-2 pt-1">
                <Badge variant="outline">{PLACEMENT_CATEGORY_LABEL[t.category]}</Badge>
                <Badge variant="secondary">{PLACEMENT_STATUS_LABEL[t.status]}</Badge>
                <Badge variant="outline">Score {t.priority_score}</Badge>
              </div>
            </DialogHeader>

            {error && <p className="rounded bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

            <section className="space-y-1 text-sm">
              <h3 className="font-semibold">Why it matters</h3>
              <ul className="list-disc pl-5 text-muted-foreground">
                {t.priority_reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
              {t.proof_question && (
                <p className="pt-1">
                  Proof question: <span className="font-medium">&ldquo;{t.proof_question.query_text}&rdquo;</span>{" "}
                  on {PLATFORM_LABELS[t.proof_question.platform] ?? t.proof_question.platform}. A placement is
                  verified when this answer starts to see the client.
                </p>
              )}
              {t.authority_asset_id && (
                <p className="text-muted-foreground">This site is already tracked in the authority checklist below.</p>
              )}
            </section>

            <section className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Page</h3>
                <Button size="sm" variant="outline" disabled={busy !== null}
                  onClick={() => act("analyze", () => analyzePlacementAction(clientId, t.id))}>
                  {busy === "analyze" ? "Checking…" : analysis ? "Check again" : "Check page"}
                </Button>
              </div>
              {!analysis ? (
                <p className="text-muted-foreground">Not checked yet. Checking reads the page and how to reach its editor.</p>
              ) : analysis.fetch_status !== "ok" ? (
                <p className="text-muted-foreground">
                  The page could not be read ({analysis.fetch_status}). Open it directly to find a contact.
                </p>
              ) : (
                <div className="space-y-1 text-muted-foreground">
                  <p>
                    {analysis.is_listicle
                      ? `Ranked list of ${analysis.entries_count} businesses.`
                      : "Not a ranked list."}
                    {analysis.site_name && ` ${analysis.site_name}.`}
                    {analysis.modified ? ` Updated ${analysis.modified}.` : analysis.published ? ` Published ${analysis.published}.` : ""}
                  </p>
                  {analysis.competitors_listed && analysis.competitors_listed.length > 0 && (
                    <p>
                      Competitors on it:{" "}
                      {analysis.competitors_listed
                        .map((c) => (c.position ? `${c.name} (#${c.position})` : c.name))
                        .join(", ")}
                    </p>
                  )}
                  <ContactRoutes contact={analysis.contact} />
                </div>
              )}
            </section>

            <section className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Outreach</h3>
                <Button size="sm" variant="outline" disabled={busy !== null}
                  onClick={() => act("draft", () => createPlacementDraftAction(clientId, t.id))}>
                  {busy === "draft" ? "Drafting…" : t.category === "directory" ? "Build submission checklist" : "Draft email"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Drafts use only the client&apos;s profile and approved Truth Vault facts. SeenBy never sends them.
              </p>
              {t.outreach_drafts.length === 0 ? (
                <p className="text-muted-foreground">No drafts yet.</p>
              ) : (
                <DraftView
                  key={t.outreach_drafts[t.outreach_drafts.length - 1].id}
                  draft={t.outreach_drafts[t.outreach_drafts.length - 1]}
                  saving={busy === "save"}
                  onSave={(subject, body) =>
                    act("save", () => editPlacementDraftAction(
                      clientId, t.id, t.outreach_drafts[t.outreach_drafts.length - 1].id, subject, body))}
                />
              )}
            </section>

            <section className="flex flex-wrap items-end gap-2 border-t pt-4 text-sm">
              {canPursue && (
                <>
                  <label className="space-y-1">
                    <span className="block text-xs text-muted-foreground">Follow up by (optional)</span>
                    <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className="w-44" />
                  </label>
                  <Button disabled={busy !== null}
                    onClick={() => act("pursue", () => pursuePlacementAction(clientId, t.id, dueDate || null))}>
                    {busy === "pursue" ? "Adding…" : "Pursue"}
                  </Button>
                </>
              )}
              {t.outcome_action_id && (
                <Button asChild variant="outline">
                  <Link href={`/clients/${clientId}/delivery`}>Open in delivery</Link>
                </Button>
              )}
              {(t.status === "open" || t.status === "stale") && (
                <Button variant="ghost" disabled={busy !== null}
                  onClick={() => act("dismiss", () => setPlacementStatusAction(clientId, t.id, "dismissed"))}>
                  Dismiss
                </Button>
              )}
              {t.status === "dismissed" && (
                <Button variant="outline" disabled={busy !== null}
                  onClick={() => act("reopen", () => setPlacementStatusAction(clientId, t.id, "open"))}>
                  Reopen
                </Button>
              )}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ContactRoutes({ contact }: { contact?: { emails: string[]; contact_pages: string[]; submission_links: string[] } }) {
  if (!contact) return null
  const none = !contact.emails.length && !contact.contact_pages.length && !contact.submission_links.length
  if (none) return <p>No contact route on the page.</p>
  return (
    <ul className="space-y-0.5">
      {contact.emails.map((e) => <li key={e}>Email: <a className="underline" href={`mailto:${e}`}>{e}</a></li>)}
      {contact.submission_links.map((u) => (
        <li key={u}>Submit: <a className="underline" href={u} target="_blank" rel="noopener noreferrer">{u}</a></li>
      ))}
      {contact.contact_pages.map((u) => (
        <li key={u}>Contact page: <a className="underline" href={u} target="_blank" rel="noopener noreferrer">{u}</a></li>
      ))}
    </ul>
  )
}

function DraftView({
  draft, saving, onSave,
}: {
  draft: PlacementDraft
  saving: boolean
  onSave: (subject: string, body: string) => void
}) {
  if (draft.kind === "checklist") {
    return (
      <div className="space-y-2 rounded border p-3">
        <ul className="space-y-0.5">
          {draft.fields.map((f) => <li key={`${f.label}-${f.value}`}><span className="font-medium">{f.label}:</span> {f.value}</li>)}
        </ul>
        {draft.gaps.length > 0 && (
          <p className="text-score-watch-fg">Missing (add to the client profile or Truth Vault first): {draft.gaps.join(", ")}</p>
        )}
        {draft.submit_at.map((u) => (
          <p key={u}>Submit at: <a className="underline" href={u} target="_blank" rel="noopener noreferrer">{u}</a></p>
        ))}
      </div>
    )
  }
  return <EmailDraft draft={draft} saving={saving} onSave={onSave} />
}

function EmailDraft({
  draft, saving, onSave,
}: {
  draft: PlacementEmailDraft
  saving: boolean
  onSave: (subject: string, body: string) => void
}) {
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [copied, setCopied] = useState(false)
  const changed = subject !== draft.subject || body !== draft.body

  return (
    <div className="space-y-2 rounded border p-3">
      {draft.needs_edit && (
        <div className="rounded bg-score-watch-bg p-2 text-score-watch-fg">
          Check before sending. Not found in the approved facts:
          <ul className="list-disc pl-5">{draft.grounding_issues.map((i) => <li key={i}>{i}</li>)}</ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground">To: {draft.to.length ? draft.to.join(", ") : "no email found on the page"}</p>
      <Input value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject" />
      <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={9} aria-label="Body" />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={!changed || saving} onClick={() => onSave(subject, body)}>
          {saving ? "Saving…" : "Save edits"}
        </Button>
        <Button size="sm" variant="outline"
          onClick={async () => {
            await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`)
            setCopied(true)
          }}>
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button size="sm" asChild>
          <a href={mailtoHref({ to: draft.to, subject, body })}>Open in mail</a>
        </Button>
      </div>
    </div>
  )
}
