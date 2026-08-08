// frontend/src/components/clients/ProspectQuickForm.tsx
// Lightweight cold-outreach create flow: name + website + industry only. It
// creates the prospect and mints a share link, but does NOT scan — scanning is
// manual from the prospect row, so leads can be added in bulk for free.
"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { createProspectAction } from "@/app/(admin)/clients/actions"
import { INDUSTRIES } from "@/lib/industries"

interface Props {
  onClose: () => void
}

export function ProspectQuickForm({ onClose }: Props) {
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [industry, setIndustry] = useState("")
  const [competitor, setCompetitor] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!industry) {
      setError("Please select an industry.")
      return
    }
    setLoading(true)
    setError(null)
    try {
      const { client } = await createProspectAction({
        name,
        website,
        industry,
        competitor,
      })
      toast.success(`${client.name} added — scan it when you're ready`)
      onClose()
    } catch {
      setError("Failed to add prospect. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  // ── Form state ──────────────────────────────────────────────────────────────
  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Just the basics — nothing runs yet. Scan the prospect from the list when
        you&apos;re ready to pitch, and add full profile details if they sign.
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="space-y-2">
        <Label htmlFor="prospect-name">Brand name *</Label>
        <Input
          id="prospect-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Acme Corp"
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="prospect-website">Website *</Label>
        <Input
          id="prospect-website"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          placeholder="https://acme.com"
          type="url"
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="prospect-industry">Industry *</Label>
        <Select value={industry} onValueChange={setIndustry}>
          <SelectTrigger id="prospect-industry">
            <SelectValue placeholder="Select industry…" />
          </SelectTrigger>
          <SelectContent>
            {INDUSTRIES.map((i) => (
              <SelectItem key={i} value={i}>
                {i}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="prospect-competitor">Main competitor</Label>
        <Input
          id="prospect-competitor"
          value={competitor}
          onChange={(e) => setCompetitor(e.target.value)}
          placeholder="Competitor name (optional)"
        />
        <p className="text-xs text-muted-foreground">
          Add one to include the head-to-head comparison when you scan — the gap
          to show on the call.
        </p>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading}>
          {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Add prospect
        </Button>
      </div>
    </form>
  )
}
