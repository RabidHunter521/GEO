"use client"

import Link from "next/link"
import { ExternalLink } from "lucide-react"
import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { OUTCOME_ACTION_STATUS_LABELS, validNextStatuses } from "@/lib/delivery-lifecycle"
import type { OutcomeAction, OutcomeActionPatch, OutcomeActionStatus } from "@/types"

export function ActionDetailDialog({
  action,
  open,
  onOpenChange,
  onPatch,
  onTransition,
}: {
  action: OutcomeAction | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onPatch: (actionId: string, patch: OutcomeActionPatch) => Promise<OutcomeAction>
  onTransition: (actionId: string, status: OutcomeActionStatus) => Promise<OutcomeAction>
}) {
  const [draft, setDraft] = useState({ owner: "", due_date: "", client_safe_summary: "", destination_url: "", approval_evidence: "", verification_scan_id: "" })
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!action) return
    setDraft({
      owner: action.owner ?? "",
      due_date: action.due_date ?? "",
      client_safe_summary: action.client_safe_summary ?? "",
      destination_url: action.destination_url ?? "",
      approval_evidence: "",
      verification_scan_id: "",
    })
    setError(null)
  }, [action])

  if (!action) return null

  const currentAction = action
  const updateDraft = (key: keyof typeof draft, value: string) => setDraft((current) => ({ ...current, [key]: value }))
  const transitionTargets = validNextStatuses(currentAction.status)
  const priorityReasons = Array.isArray(action.priority_reasons?.reasons) ? action.priority_reasons.reasons : []

  async function save() {
    setPending(true); setError(null)
    try {
      await onPatch(currentAction.id, {
        owner: draft.owner || null,
        due_date: draft.due_date || null,
        client_safe_summary: draft.client_safe_summary || null,
        destination_url: draft.destination_url || null,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save this action.")
    } finally { setPending(false) }
  }

  async function transition(status: OutcomeActionStatus) {
    setPending(true); setError(null)
    try {
      if (status === "published" || status === "verified" || status === "no_change") {
        await onPatch(currentAction.id, {
          ...(draft.destination_url ? { destination_url: draft.destination_url } : {}),
          ...(draft.approval_evidence ? { approval_decision: "approved", approval_evidence: draft.approval_evidence } : {}),
          ...((status === "verified" || status === "no_change") && draft.verification_scan_id
            ? { verification_result: { scan_id: draft.verification_scan_id, basis: status === "verified" ? "visibility_change" : "no_change" } }
            : {}),
        })
      }
      await onTransition(currentAction.id, status)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update the lifecycle.")
    } finally { setPending(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{action.title}</DialogTitle>
          <DialogDescription>Manage the reviewed delivery action and its lifecycle.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div><p className="text-xs text-muted-foreground">Type</p><p className="text-sm font-medium">{action.action_type.replaceAll("_", " ")}</p></div>
          <div><p className="text-xs text-muted-foreground">Status</p><Badge variant="secondary">{OUTCOME_ACTION_STATUS_LABELS[action.status]}</Badge></div>
          <div><p className="text-xs text-muted-foreground">Priority</p><p className="text-sm font-medium">{action.priority}</p></div>
          <div><p className="text-xs text-muted-foreground">Confidence</p><p className="text-sm font-medium">{action.confidence}</p></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1"><Label htmlFor="owner">Owner</Label><Input id="owner" value={draft.owner} onChange={(e) => updateDraft("owner", e.target.value)} /></div>
          <div className="space-y-1"><Label htmlFor="due-date">Due date</Label><Input id="due-date" type="date" value={draft.due_date} onChange={(e) => updateDraft("due_date", e.target.value)} /></div>
          <div className="space-y-1 sm:col-span-2"><Label htmlFor="destination">Destination URL</Label><Input id="destination" type="url" value={draft.destination_url} onChange={(e) => updateDraft("destination_url", e.target.value)} /></div>
          <div className="space-y-1 sm:col-span-2"><Label htmlFor="summary">Reviewed summary</Label><Textarea id="summary" value={draft.client_safe_summary} onChange={(e) => updateDraft("client_safe_summary", e.target.value)} /></div>
        </div>
        <div className="grid gap-3 rounded-md border p-3 text-sm sm:grid-cols-3">
          <p><span className="block text-xs text-muted-foreground">Source evidence</span>{action.source_kind.replaceAll("_", " ")}{action.source_ref ? `: ${action.source_ref}` : ""}</p>
          <p><span className="block text-xs text-muted-foreground">Rationale</span>{action.rationale}</p>
          <p><span className="block text-xs text-muted-foreground">Priority reasons</span>{priorityReasons.length ? priorityReasons.join("; ") : "No scored reasons recorded."}</p>
          <p><span className="block text-xs text-muted-foreground">Verification result</span>{action.verification_result ? `${action.verification_result.basis.replaceAll("_", " ")} scan ${action.verification_result.scan_id}` : action.verified_at ? `Recorded ${new Date(action.verified_at).toLocaleDateString("en-MY")}` : "Not recorded"}</p>
          {action.content_deliverable_id && <Link className="inline-flex items-center gap-1 text-primary hover:underline" href={`/clients/${action.client_id}/content-studio`}>Open deliverable <ExternalLink className="h-3 w-3" /></Link>}
          {action.destination_url && <a className="inline-flex items-center gap-1 text-primary hover:underline" href={action.destination_url} target="_blank" rel="noreferrer">Open destination <ExternalLink className="h-3 w-3" /></a>}
        </div>
        {(transitionTargets.includes("published") || transitionTargets.includes("verified") || transitionTargets.includes("no_change")) && (
          <div className="grid gap-3 rounded-md border p-3">
            <div className="space-y-1"><Label htmlFor="approval">Approval evidence</Label><Textarea id="approval" value={draft.approval_evidence} onChange={(e) => updateDraft("approval_evidence", e.target.value)} /></div>
            {(transitionTargets.includes("verified") || transitionTargets.includes("no_change")) && <div className="space-y-1"><Label htmlFor="verification-scan">Completed verification scan ID</Label><Input id="verification-scan" value={draft.verification_scan_id} onChange={(e) => updateDraft("verification_scan_id", e.target.value)} /></div>}
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex flex-wrap justify-between gap-2 border-t pt-4">
          <Button variant="outline" disabled={pending} onClick={save}>Save changes</Button>
          <div className="flex flex-wrap gap-2">
            {transitionTargets.map((status) => <Button key={status} disabled={pending} variant={status === "dismissed" ? "outline" : "default"} onClick={() => transition(status)}>{OUTCOME_ACTION_STATUS_LABELS[status]}</Button>)}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
