"use client"

import { useState, useTransition } from "react"
import { AlertTriangle } from "lucide-react"

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  INDUSTRY_PACKS, impactOfPackChange, subcategoriesFor, subcategoryLabel,
} from "@/lib/industry-packs"
import type { Client } from "@/types"

import { updateClientAction } from "./actions"

const NONE = "__none__"

/**
 * Industry pack selection.
 *
 * Saves on its own rather than through the main settings form, because a pack
 * change is not an ordinary field edit: it changes which questions the client
 * is scanned on and makes prior scans non-comparable. The backend enforces
 * this too (409 without confirm_pack_change) — this dialog exists so the admin
 * sees WHAT changes before agreeing, not so the rule lives in the UI.
 */
export function IndustryPackCard({ client }: { client: Client }) {
  const [pack, setPack] = useState<string | null>(client.industry_pack)
  const [subcategory, setSubcategory] = useState<string | null>(client.industry_subcategory)
  const [saved, setSaved] = useState<{ pack: string | null; subcategory: string | null }>({
    pack: client.industry_pack,
    subcategory: client.industry_subcategory,
  })
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()

  const subcategories = subcategoriesFor(pack)
  const isPackChange = saved.pack !== null && pack !== saved.pack
  const dirty = pack !== saved.pack || subcategory !== saved.subcategory

  function persist(confirmPackChange: boolean) {
    setError(null)
    startTransition(async () => {
      try {
        await updateClientAction(client.id, {
          industry_pack: pack,
          industry_subcategory: subcategory,
          ...(confirmPackChange ? { confirm_pack_change: true } : {}),
        })
        setSaved({ pack, subcategory })
        setConfirming(false)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not save the pack selection.")
      }
    })
  }

  function submit() {
    // A first-time selection changes nothing that already exists, so it saves
    // straight through — only a SWITCH needs the preview.
    if (isPackChange) setConfirming(true)
    else persist(false)
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold tracking-tight">Industry pack</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Specialises this client&apos;s buyer questions, the business facts we track, and how
          accuracy issues are prioritised. Without a pack the client uses the standard
          question set.
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="s-industry-pack">Pack</Label>
          <Select
            value={pack ?? NONE}
            onValueChange={(value) => {
              const next = value === NONE ? null : value
              setPack(next)
              // A subcategory from the old pack is meaningless under the new one.
              if (next !== pack) setSubcategory(null)
            }}
          >
            <SelectTrigger id="s-industry-pack">
              <SelectValue placeholder="No pack selected" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>No pack (standard questions)</SelectItem>
              {INDUSTRY_PACKS.map((definition) => (
                <SelectItem key={definition.key} value={definition.key}>
                  {definition.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="s-industry-subcategory">Subcategory</Label>
          <Select
            value={subcategory ?? NONE}
            disabled={subcategories.length === 0}
            onValueChange={(value) => setSubcategory(value === NONE ? null : value)}
          >
            <SelectTrigger id="s-industry-subcategory">
              <SelectValue placeholder={pack ? "Select a subcategory" : "Select a pack first"} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Not set</SelectItem>
              {subcategories.map((value) => (
                <SelectItem key={value} value={value}>{subcategoryLabel(value)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" size="sm" disabled={!dirty || pending} onClick={submit}>
          {pending ? "Saving…" : "Save pack"}
        </Button>
        {client.industry_pack_version && (
          <Badge variant="secondary">
            Pack version {client.industry_pack_version}
          </Badge>
        )}
        {saved.pack === null && (
          <span className="text-xs text-muted-foreground">
            No pack reviewed yet — using the standard question set.
          </span>
        )}
      </div>

      <PackChangeDialog
        open={confirming}
        pending={pending}
        fromKey={saved.pack}
        toKey={pack}
        onCancel={() => {
          setConfirming(false)
          // Cancelling must leave nothing changed, including in the form.
          setPack(saved.pack)
          setSubcategory(saved.subcategory)
        }}
        onConfirm={() => persist(true)}
      />
    </section>
  )
}

function PackChangeDialog({
  open, pending, fromKey, toKey, onCancel, onConfirm,
}: {
  open: boolean
  pending: boolean
  fromKey: string | null
  toKey: string | null
  onCancel: () => void
  onConfirm: () => void
}) {
  const impact = impactOfPackChange(fromKey, toKey)
  const retiredTypes = [...new Set(impact.retiredFields.map((f) => f.factType))]
  const newTypes = [...new Set(impact.newFields.map((f) => f.factType))]

  return (
    <AlertDialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" aria-hidden />
            Change pack from {impact.from} to {impact.to}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            This changes which questions this client is scanned on, so results after the
            change are not directly comparable with results before it.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <dl className="my-2 space-y-2 rounded-md bg-muted p-3 text-sm">
          <Row label="Approved facts">
            Kept. Nothing is deleted — {impact.sharedFields.length} field
            {impact.sharedFields.length === 1 ? "" : "s"} carry over, and facts the new pack
            does not track are simply no longer asked about.
          </Row>
          {retiredTypes.length > 0 && (
            <Row label="No longer tracked">{retiredTypes.join(", ")}</Row>
          )}
          {newTypes.length > 0 && (
            <Row label="Newly tracked">{newTypes.join(", ")}</Row>
          )}
          <Row label="Subcategory">Cleared — you will need to choose one for the new pack.</Row>
          <Row label="Benchmarks">Reset, because query coverage changes.</Row>
        </dl>

        <AlertDialogFooter>
          <AlertDialogCancel type="button" disabled={pending} onClick={onCancel}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction type="button" disabled={pending} onClick={onConfirm}>
            {pending ? "Changing…" : "Change pack"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="inline font-medium">{label}: </dt>
      <dd className="inline text-muted-foreground">{children}</dd>
    </div>
  )
}
