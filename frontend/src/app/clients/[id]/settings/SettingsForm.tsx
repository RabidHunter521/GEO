// frontend/src/app/clients/[id]/settings/SettingsForm.tsx
"use client"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Loader2, CheckCircle, Plus, Trash2 } from "lucide-react"
import { updateClientAction } from "./actions"
import {
  addCompetitorAction,
  deleteCompetitorAction,
} from "@/app/clients/actions"
import type { Client, Competitor } from "@/types"

interface Props {
  client: Client
  competitors: Competitor[]
}

const INDUSTRIES = [
  "Technology", "SaaS", "E-commerce", "Healthcare", "Finance",
  "Education", "Real Estate", "Food & Beverage", "Retail", "Other",
]

export function SettingsForm({ client, competitors: initialCompetitors }: Props) {
  const [isPending, startTransition] = useTransition()
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [competitors, setCompetitors] = useState<Competitor[]>(initialCompetitors)
  const [compName, setCompName] = useState("")
  const [compWebsite, setCompWebsite] = useState("")
  const [addingComp, setAddingComp] = useState(false)

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setError(null)
    setSaved(false)
    startTransition(async () => {
      try {
        await updateClientAction(client.id, {
          name: fd.get("name") as string,
          website: fd.get("website") as string,
          industry: fd.get("industry") as string,
          description: (fd.get("description") as string) || undefined,
          target_audience: (fd.get("target_audience") as string) || undefined,
          city: (fd.get("city") as string) || undefined,
          state: (fd.get("state") as string) || undefined,
          contact_email: (fd.get("contact_email") as string) || undefined,
          brand_authority_score: fd.get("brand_authority_score")
            ? Number(fd.get("brand_authority_score"))
            : undefined,
          content_quality_score: fd.get("content_quality_score")
            ? Number(fd.get("content_quality_score"))
            : undefined,
          score_drop_threshold: fd.get("score_drop_threshold")
            ? Number(fd.get("score_drop_threshold"))
            : undefined,
        })
        setSaved(true)
      } catch {
        setError("Failed to save. Please try again.")
      }
    })
  }

  async function handleAddComp() {
    if (!compName.trim()) return
    setAddingComp(true)
    try {
      const comp = await addCompetitorAction(client.id, {
        name: compName.trim(),
        website: compWebsite.trim() || undefined,
      })
      setCompetitors((prev) => [...prev, comp])
      setCompName("")
      setCompWebsite("")
    } catch {
      setError("Failed to add competitor.")
    } finally {
      setAddingComp(false)
    }
  }

  async function handleRemoveComp(id: string) {
    try {
      await deleteCompetitorAction(client.id, id)
      setCompetitors((prev) => prev.filter((c) => c.id !== id))
    } catch {
      setError("Failed to remove competitor.")
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-8">
      {/* Brand details */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">Brand Details</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 space-y-1">
            <Label htmlFor="s-name">Brand name</Label>
            <Input id="s-name" name="name" defaultValue={client.name} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-website">Website</Label>
            <Input id="s-website" name="website" defaultValue={client.website} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-industry">Industry</Label>
            <select
              id="s-industry"
              name="industry"
              defaultValue={client.industry}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <Separator />

      {/* Profile */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">Profile</h2>
        <div className="space-y-1">
          <Label htmlFor="s-desc">Description</Label>
          <textarea
            id="s-desc"
            name="description"
            defaultValue={client.description ?? ""}
            rows={3}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-audience">Target audience</Label>
          <Input
            id="s-audience"
            name="target_audience"
            defaultValue={client.target_audience ?? ""}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-city">City</Label>
            <Input id="s-city" name="city" defaultValue={client.city ?? ""} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-state">State</Label>
            <Input id="s-state" name="state" defaultValue={client.state ?? ""} />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-email">Contact email</Label>
          <Input
            id="s-email"
            name="contact_email"
            type="email"
            defaultValue={client.contact_email ?? ""}
          />
        </div>
      </section>

      <Separator />

      {/* Manual scores */}
      <section className="space-y-4">
        <div>
          <h2 className="text-base font-semibold">Manual Score Inputs</h2>
          <p className="text-xs text-muted-foreground mt-0.5 italic">
            Assessed by SeenBy team
          </p>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-authority">Brand Authority (0–100)</Label>
            <Input
              id="s-authority"
              name="brand_authority_score"
              type="number"
              min="0"
              max="100"
              defaultValue={client.brand_authority_score}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-content">Content Quality (0–100)</Label>
            <Input
              id="s-content"
              name="content_quality_score"
              type="number"
              min="0"
              max="100"
              defaultValue={client.content_quality_score}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-threshold">Score Drop Threshold</Label>
            <Input
              id="s-threshold"
              name="score_drop_threshold"
              type="number"
              min="0"
              max="100"
              defaultValue={client.score_drop_threshold}
            />
          </div>
        </div>
      </section>

      <Separator />

      {/* Competitors */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">
          Competitors ({competitors.length}/5)
        </h2>
        {competitors.length > 0 && (
          <ul className="space-y-2">
            {competitors.map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-medium">{c.name}</span>
                  {c.website && (
                    <span className="text-muted-foreground ml-2">{c.website}</span>
                  )}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRemoveComp(c.id)}
                  className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {competitors.length < 5 && (
          <div className="flex gap-2 items-end">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Name</Label>
              <Input
                value={compName}
                onChange={(e) => setCompName(e.target.value)}
                placeholder="Rival Co"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Website (optional)</Label>
              <Input
                value={compWebsite}
                onChange={(e) => setCompWebsite(e.target.value)}
                placeholder="https://rival.com"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={handleAddComp}
              disabled={addingComp || !compName.trim()}
            >
              {addingComp ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
            </Button>
          </div>
        )}
      </section>

      {/* Save footer */}
      <div className="flex items-center gap-3 pt-2">
        <Button type="submit" disabled={isPending}>
          {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Save changes
        </Button>
        {saved && (
          <span className="flex items-center gap-1 text-sm text-green-600">
            <CheckCircle className="h-4 w-4" />
            Saved
          </span>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </form>
  )
}
