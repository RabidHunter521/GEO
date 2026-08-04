"use client"

import { FormEvent, useState } from "react"
import { Pencil, Plus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { PackFactField } from "@/lib/industry-packs"
import type { TruthFact, TruthFactDraftInput, TruthFactVersion } from "@/types"
import { FactHistory } from "./FactHistory"

type DraftValues = {
  factKey: string
  displayValue: string
  rawValue: string
  sourceUrl: string
  effectiveFrom: string
}

function defaultDraft(fact?: TruthFact): DraftValues {
  const latest = fact?.versions[0]
  const raw = latest?.value.value
  return {
    factKey: fact?.fact_key ?? "",
    displayValue: latest?.value.display_value ?? "",
    rawValue: typeof raw === "string" ? raw : raw == null ? "" : JSON.stringify(raw),
    sourceUrl: latest?.source_url ?? "",
    effectiveFrom: new Date().toISOString().slice(0, 16),
  }
}

function draftInput(values: DraftValues): TruthFactDraftInput {
  let value: string | number | boolean | unknown[] | Record<string, unknown> | null = values.rawValue
  const trimmed = values.rawValue.trim()
  if (!trimmed) value = null
  else if (/^(?:\[|\{|true$|false$|-?\d)/.test(trimmed)) {
    try { value = JSON.parse(trimmed) } catch { value = values.rawValue }
  }
  return {
    value: { value, display_value: values.displayValue.trim() },
    source_url: values.sourceUrl.trim() || null,
    effective_from: new Date(values.effectiveFrom).toISOString(),
  }
}

export function FactEditor({
  title, factType, facts, locationId, pending, packFields = [],
  onCreateFact, onDraftVersion, onApproveVersion,
}: {
  title: string
  factType: string
  facts: TruthFact[]
  locationId: string | null
  pending?: boolean
  /** Field definitions from the client's industry pack, when it has one. */
  packFields?: readonly PackFactField[]
  onCreateFact: (input: Pick<TruthFact, "fact_type" | "fact_key" | "location_id">) => Promise<TruthFact>
  onDraftVersion: (factId: string, input: TruthFactDraftInput) => Promise<TruthFactVersion>
  onApproveVersion: (factId: string, versionId: string, approvedBy: string) => Promise<TruthFactVersion>
}) {
  const [editing, setEditing] = useState<TruthFact | "new" | null>(null)
  const [approving, setApproving] = useState<{ fact: TruthFact; version: TruthFactVersion } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function save(values: DraftValues) {
    setError(null)
    try {
      const fact = editing === "new"
        ? await onCreateFact({ fact_type: factType, fact_key: values.factKey.trim(), location_id: locationId })
        : editing
      if (!fact) return
      await onDraftVersion(fact.id, draftInput(values))
      setEditing(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save the draft.")
    }
  }

  async function approve(approvedBy: string) {
    if (!approving) return
    setError(null)
    try {
      await onApproveVersion(approving.fact.id, approving.version.id, approvedBy)
      setApproving(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not approve this draft.")
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div><CardTitle className="text-base">{title}</CardTitle><p className="mt-1 text-sm text-muted-foreground">Versioned {title.toLowerCase()} facts for this scope.</p></div>
        <Button size="sm" onClick={() => setEditing("new")} disabled={pending}><Plus className="mr-1.5 h-3.5 w-3.5" />Add fact</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        {facts.length === 0 ? <p className="text-sm text-muted-foreground">No {title.toLowerCase()} facts yet.</p> : facts.map((fact) => {
          const latest = fact.versions[0]
          const draft = fact.versions.find((version) => version.status === "draft")
          const definition = packFields.find((field) => field.key === fact.fact_key)
          return <div key={fact.id} className="space-y-3 rounded-md border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{definition?.label ?? fact.fact_key}</span>
              {definition?.riskSensitive && (
                <Badge variant="outline" className="border-amber-500/50 text-amber-600">
                  Needs a source
                </Badge>
              )}
              {latest && <span className="text-sm text-muted-foreground">{latest.value.display_value}</span>}
              {draft && <Badge variant="secondary">Draft awaiting approval</Badge>}
              <Button size="sm" variant="outline" className="ml-auto" disabled={pending} onClick={() => setEditing(fact)}><Pencil className="mr-1.5 h-3.5 w-3.5" />Edit</Button>
              {draft && <Button size="sm" disabled={pending} onClick={() => setApproving({ fact, version: draft })}>Approve draft</Button>}
            </div>
            <FactHistory fact={fact} />
          </div>
        })}
      </CardContent>

      <DraftDialog
        key={editing === "new" ? "new" : editing?.id ?? "closed"}
        open={editing !== null}
        fact={editing === "new" ? undefined : editing ?? undefined}
        title={title}
        pending={pending}
        packFields={packFields}
        takenKeys={facts.map((fact) => fact.fact_key)}
        onOpenChange={(open) => !open && setEditing(null)}
        onSave={save}
      />
      <ApprovalDialog
        open={approving !== null}
        pending={pending}
        draft={approving?.version ?? null}
        onOpenChange={(open) => !open && setApproving(null)}
        onApprove={approve}
      />
    </Card>
  )
}

/** Placeholder and hint appropriate to a pack field's declared value type. */
function valueHelp(field?: PackFactField): { placeholder: string; hint?: string } {
  switch (field?.valueType) {
    case "boolean": return { placeholder: "true or false", hint: "Enter true or false." }
    case "number": return { placeholder: "12", hint: "Enter a number." }
    case "url": return { placeholder: "https://example.com/page", hint: "Enter an absolute URL." }
    case "list": return {
      placeholder: '["first item", "second item"]',
      hint: "Enter a JSON array, one entry per item.",
    }
    case "hours": return {
      placeholder: '{"monday": "09:00-18:00"}',
      hint: "Enter opening times as JSON, keyed by day.",
    }
    default: return { placeholder: "Plain text or valid JSON" }
  }
}

function DraftDialog({
  open, fact, title, pending, packFields = [], takenKeys = [], onOpenChange, onSave,
}: {
  open: boolean
  fact?: TruthFact
  title: string
  pending?: boolean
  packFields?: readonly PackFactField[]
  takenKeys?: readonly string[]
  onOpenChange: (open: boolean) => void
  onSave: (values: DraftValues) => Promise<void>
}) {
  const [values, setValues] = useState(() => defaultDraft(fact))
  const [saving, setSaving] = useState(false)
  const update = (field: keyof DraftValues, value: string) => setValues((current) => ({ ...current, [field]: value }))

  const definition = packFields.find((field) => field.key === values.factKey)
  // A risk-sensitive fact is one a client could be harmed by us repeating
  // wrongly, so it may not be drafted without something to check it against.
  const sourceRequired = definition?.riskSensitive === true
  const help = valueHelp(definition)
  // Only offer keys not already present; the Vault enforces one fact per
  // (type, key) per scope, so offering a taken key just produces an error.
  const available = packFields.filter((field) => !takenKeys.includes(field.key))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!values.factKey.trim() || !values.displayValue.trim() || !values.effectiveFrom) return
    if (sourceRequired && !values.sourceUrl.trim()) return
    setSaving(true)
    try { await onSave(values) } finally { setSaving(false) }
  }
  const disabled = pending || saving
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="sm:max-w-xl"><DialogHeader><DialogTitle>{fact ? `Draft a revision for ${fact.fact_key}` : `Add ${title.toLowerCase()} fact`}</DialogTitle><DialogDescription>Saving creates a draft only. It cannot become current until separately approved.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}>
    {!fact && (packFields.length > 0 ? (
      <div className="space-y-1.5">
        <Label htmlFor="truth-fact-key">Fact *</Label>
        <Select value={values.factKey} onValueChange={(value) => update("factKey", value)}>
          <SelectTrigger id="truth-fact-key"><SelectValue placeholder="Select a fact to record" /></SelectTrigger>
          <SelectContent>
            {available.map((field) => (
              <SelectItem key={field.key} value={field.key}>
                {field.label}{field.riskSensitive ? " — needs a source" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {available.length === 0
            ? "Every fact this pack tracks for this group already exists."
            : "These are the facts this client's industry pack tracks."}
        </p>
      </div>
    ) : (
      <Field label="Fact key" value={values.factKey} required onChange={(value) => update("factKey", value)} hint="Use a stable key such as official_name, booking_url, or cancellation_policy." />
    ))}
    <Field label="Display value" value={values.displayValue} required onChange={(value) => update("displayValue", value)} />
    <div className="space-y-1.5"><Label htmlFor="truth-raw-value">Stored value</Label><Textarea id="truth-raw-value" value={values.rawValue} onChange={(event) => update("rawValue", event.target.value)} placeholder={help.placeholder} />{help.hint && <p className="text-xs text-muted-foreground">{help.hint}</p>}</div>
    <Field
      label="Source URL"
      type="url"
      value={values.sourceUrl}
      required={sourceRequired}
      onChange={(value) => update("sourceUrl", value)}
      hint={sourceRequired
        ? "Required: this fact carries real-world risk if we repeat it wrongly, so it must be checkable."
        : "Use an absolute HTTP(S) source when available."}
    />
    <Field label="Effective from" type="datetime-local" value={values.effectiveFrom} required onChange={(value) => update("effectiveFrom", value)} />
    <DialogFooter><Button type="button" variant="outline" disabled={disabled} onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={disabled}>{saving ? "Saving…" : "Save draft"}</Button></DialogFooter>
  </form></DialogContent></Dialog>
}

function ApprovalDialog({ open, pending, draft, onOpenChange, onApprove }: {
  open: boolean
  pending?: boolean
  draft: TruthFactVersion | null
  onOpenChange: (open: boolean) => void
  onApprove: (approvedBy: string) => Promise<void>
}) {
  const [approvedBy, setApprovedBy] = useState("")
  const [saving, setSaving] = useState(false)
  async function approve(event: FormEvent) {
    event.preventDefault()
    if (!approvedBy.trim()) return
    setSaving(true)
    try { await onApprove(approvedBy.trim()) } finally { setSaving(false) }
  }
  return <AlertDialog open={open} onOpenChange={onOpenChange}><AlertDialogContent><form onSubmit={approve}><AlertDialogHeader><AlertDialogTitle>Approve this draft?</AlertDialogTitle><AlertDialogDescription>This will make the draft eligible as the current fact from its effective date. Confirm its source and effective date before approving.</AlertDialogDescription></AlertDialogHeader><dl className="my-4 space-y-1 rounded-md bg-muted p-3 text-sm"><div><dt className="inline font-medium">Value: </dt><dd className="inline">{draft?.value.display_value}</dd></div><div><dt className="inline font-medium">Source: </dt><dd className="inline">{draft?.source_url ?? "No source URL recorded"}</dd></div><div><dt className="inline font-medium">Effective from: </dt><dd className="inline">{draft?.effective_from ? new Date(draft.effective_from).toLocaleString() : "Not set"}</dd></div></dl><div className="space-y-1.5"><Label htmlFor="truth-approved-by">Approved by</Label><Input id="truth-approved-by" required value={approvedBy} onChange={(event) => setApprovedBy(event.target.value)} placeholder="Your name" /></div><AlertDialogFooter className="mt-4"><AlertDialogCancel type="button" disabled={pending || saving}>Cancel</AlertDialogCancel><AlertDialogAction type="submit" disabled={pending || saving}>{saving ? "Approving…" : "Approve draft"}</AlertDialogAction></AlertDialogFooter></form></AlertDialogContent></AlertDialog>
}

function Field({ label, hint, value, required, type = "text", onChange }: { label: string; hint?: string; value: string; required?: boolean; type?: string; onChange: (value: string) => void }) {
  const id = `truth-${label.toLowerCase().replaceAll(" ", "-")}`
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}{required ? " *" : ""}</Label><Input id={id} type={type} value={value} required={required} onChange={(event) => onChange(event.target.value)} />{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</div>
}
