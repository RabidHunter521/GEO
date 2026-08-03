"use client"

import { FormEvent, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { MapPin, Pencil, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import type { BusinessLocation, BusinessLocationInput } from "@/types"
import { primaryReplacementCandidates } from "@/lib/truth-vault"

type FormData = Required<Pick<BusinessLocationInput, "name">> & BusinessLocationInput

function blankLocation(): FormData {
  return { name: "", country: "MY", is_primary: false }
}

function fromLocation(location: BusinessLocation): FormData {
  return {
    name: location.name,
    is_primary: location.is_primary,
    website: location.website,
    address_line_1: location.address_line_1,
    address_line_2: location.address_line_2,
    city: location.city,
    state: location.state,
    postcode: location.postcode,
    country: location.country,
    phone: location.phone,
    booking_url: location.booking_url,
  }
}

function cleanInput(input: FormData): FormData {
  const nullable = (value: string | null | undefined) => value?.trim() || null
  return {
    ...input,
    name: input.name.trim(),
    website: nullable(input.website),
    address_line_1: nullable(input.address_line_1),
    address_line_2: nullable(input.address_line_2),
    city: nullable(input.city),
    state: nullable(input.state),
    postcode: nullable(input.postcode),
    country: input.country?.trim().toUpperCase() || null,
    phone: nullable(input.phone),
    booking_url: nullable(input.booking_url),
  }
}

export function LocationSelector({
  locations, selectedLocationId, pending, onCreate, onUpdate, onDeactivate,
}: {
  locations: BusinessLocation[]
  selectedLocationId: string | null
  pending?: boolean
  onCreate: (input: FormData) => Promise<void>
  onUpdate: (locationId: string, input: FormData) => Promise<void>
  onDeactivate: (location: BusinessLocation, replacementId: string | null) => Promise<void>
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [editing, setEditing] = useState<BusinessLocation | "new" | null>(null)
  const [deactivating, setDeactivating] = useState<BusinessLocation | null>(null)
  const [replacementId, setReplacementId] = useState("")

  function beginDeactivation(location: BusinessLocation) {
    const replacement = location.is_primary
      ? primaryReplacementCandidates(locations, location.id)[0]
      : undefined
    setReplacementId(replacement?.id ?? "")
    setDeactivating(location)
  }

  function select(locationId: string | null) {
    const params = new URLSearchParams(searchParams.toString())
    if (locationId) params.set("location", locationId)
    else params.delete("location")
    const query = params.toString()
    router.push(query ? `${pathname}?${query}` : pathname)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        size="sm"
        variant={selectedLocationId === null ? "default" : "outline"}
        onClick={() => select(null)}
      >
        Brand-wide
      </Button>
      {locations.map((location) => (
        <div key={location.id} className="flex items-center rounded-md border">
          <Button
            type="button"
            size="sm"
            variant={selectedLocationId === location.id ? "default" : "ghost"}
            className="rounded-r-none"
            onClick={() => select(location.id)}
          >
            <MapPin className="mr-1.5 h-3.5 w-3.5" />
            {location.name}{location.is_primary ? " (Primary)" : ""}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-l-none"
            aria-label={`Edit ${location.name}`}
            onClick={() => setEditing(location)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={() => setEditing("new")}>
        <Plus className="mr-1.5 h-3.5 w-3.5" /> Add location
      </Button>

      <LocationDialog
        key={editing === "new" ? "new" : editing?.id ?? "closed"}
        location={editing === "new" ? null : editing}
        locations={locations}
        open={editing !== null}
        pending={pending}
        onOpenChange={(open) => !open && setEditing(null)}
        onSave={async (input) => {
          if (editing === "new") await onCreate(input)
          else if (editing) await onUpdate(editing.id, input)
          setEditing(null)
        }}
        onDeactivate={editing && editing !== "new" ? async () => {
          beginDeactivation(editing)
          setEditing(null)
        } : undefined}
      />

      <AlertDialog open={deactivating !== null} onOpenChange={(open) => !open && setDeactivating(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Deactivate location?</AlertDialogTitle>
            <AlertDialogDescription>
              {deactivating?.is_primary
                ? "Choose and confirm a replacement primary location before deactivating this one."
                : `${deactivating?.name} will be removed from active fact administration. Its historical facts remain intact.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deactivating?.is_primary && (
            <div className="space-y-1.5">
              <Label htmlFor="primary-replacement">New primary location</Label>
              <select
                id="primary-replacement"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={replacementId}
                onChange={(event) => setReplacementId(event.target.value)}
              >
                <option value="" disabled>Select a replacement</option>
                {primaryReplacementCandidates(locations, deactivating.id).map((location) => (
                  <option key={location.id} value={location.id}>{location.name}</option>
                ))}
              </select>
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={pending || (deactivating?.is_primary === true && !replacementId)}
              onClick={async (event) => {
                event.preventDefault()
                if (!deactivating) return
                if (deactivating.is_primary && !replacementId) return
                await onDeactivate(deactivating, deactivating.is_primary ? replacementId : null)
                setDeactivating(null)
              }}
            >
              Deactivate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function LocationDialog({
  location, locations, open, pending, onOpenChange, onSave, onDeactivate,
}: {
  location: BusinessLocation | null
  locations: BusinessLocation[]
  open: boolean
  pending?: boolean
  onOpenChange: (open: boolean) => void
  onSave: (input: FormData) => Promise<void>
  onDeactivate?: () => void
}) {
  const [input, setInput] = useState<FormData>(() => location ? fromLocation(location) : blankLocation())
  const [confirmPrimary, setConfirmPrimary] = useState(false)
  const [saving, setSaving] = useState(false)
  const currentPrimary = locations.find((item) => item.is_primary)
  const movesPrimary = input.is_primary && currentPrimary?.id !== location?.id

  function update(field: keyof FormData, value: string | boolean) {
    setInput((current) => ({ ...current, [field]: value }))
  }

  async function save() {
    setSaving(true)
    try {
      await onSave(cleanInput(input))
    } finally {
      setSaving(false)
      setConfirmPrimary(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!input.name.trim()) return
    if (movesPrimary) setConfirmPrimary(true)
    else void save()
  }

  const disabled = pending || saving
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{location ? `Edit ${location.name}` : "Add location"}</DialogTitle>
          <DialogDescription>Locations keep local facts, addresses, contact channels, and sources separate from brand-wide information.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Location name" required value={input.name} onChange={(value) => update("name", value)} />
            <Field label="Website" type="url" value={input.website ?? ""} onChange={(value) => update("website", value)} />
            <Field label="Phone" type="tel" value={input.phone ?? ""} onChange={(value) => update("phone", value)} />
            <Field label="Booking URL" type="url" value={input.booking_url ?? ""} onChange={(value) => update("booking_url", value)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Address line 1" value={input.address_line_1 ?? ""} onChange={(value) => update("address_line_1", value)} />
            <Field label="Address line 2" value={input.address_line_2 ?? ""} onChange={(value) => update("address_line_2", value)} />
            <Field label="City" value={input.city ?? ""} onChange={(value) => update("city", value)} />
            <Field label="State" value={input.state ?? ""} onChange={(value) => update("state", value)} />
            <Field label="Postcode" value={input.postcode ?? ""} onChange={(value) => update("postcode", value)} />
            <Field label="Country code" hint="Two-letter code, e.g. MY" value={input.country ?? ""} onChange={(value) => update("country", value)} />
          </div>
          <label className="flex items-center gap-2 text-sm font-medium">
            <Checkbox
              checked={input.is_primary}
              disabled={location?.is_primary === true}
              onCheckedChange={(checked) => update("is_primary", checked === true)}
            />
            Make this the primary location
          </label>
          {location?.is_primary && <p className="text-xs text-muted-foreground">Assign another active location as primary before changing this one.</p>}
          <DialogFooter className="gap-2 sm:gap-0">
            {onDeactivate && <Button type="button" variant="destructive" className="sm:mr-auto" disabled={disabled} onClick={onDeactivate}><Trash2 className="mr-1.5 h-3.5 w-3.5" />Deactivate</Button>}
            <Button type="button" variant="outline" disabled={disabled} onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={disabled}>{saving ? "Saving…" : "Save location"}</Button>
          </DialogFooter>
        </form>
        <AlertDialog open={confirmPrimary} onOpenChange={setConfirmPrimary}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Reassign primary location?</AlertDialogTitle>
              <AlertDialogDescription>
                {currentPrimary ? `${currentPrimary.name} will no longer be the primary location.` : "This location will become the primary location."}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={disabled}>Keep current primary</AlertDialogCancel>
              <AlertDialogAction disabled={disabled} onClick={(event) => { event.preventDefault(); void save() }}>Confirm reassignment</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, hint, value, required, type = "text", onChange }: {
  label: string
  hint?: string
  value: string
  required?: boolean
  type?: string
  onChange: (value: string) => void
}) {
  const id = `location-${label.toLowerCase().replaceAll(" ", "-")}`
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}{required ? " *" : ""}</Label><Input id={id} type={type} value={value} required={required} onChange={(event) => onChange(event.target.value)} />{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</div>
}
