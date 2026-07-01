// frontend/src/components/clients/ProspectQuickForm.tsx
// Lightweight cold-outreach create flow: name + website + industry only. On
// submit it creates the prospect, mints a share link, and triggers a scan in
// one shot, then hands back a copy-ready link to send the lead.
"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Copy, ExternalLink, Loader2 } from "lucide-react"
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
import { createProspectAction } from "@/app/clients/actions"
import { INDUSTRIES } from "@/lib/industries"
import { copyToClipboard } from "@/lib/utils"
import type { Client } from "@/types"

interface Props {
  onClose: () => void
}

export function ProspectQuickForm({ onClose }: Props) {
  const router = useRouter()
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [industry, setIndustry] = useState("")
  const [competitor, setCompetitor] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Result state — once created we swap the form for the sendable link.
  const [createdClient, setCreatedClient] = useState<Client | null>(null)
  const [token, setToken] = useState<string | null>(null)

  // window is unavailable during SSR of this client component.
  const [origin, setOrigin] = useState("")
  useEffect(() => setOrigin(window.location.origin), [])
  const url = token && origin ? `${origin}/view/${token}` : null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!industry) {
      setError("Please select an industry.")
      return
    }
    setLoading(true)
    setError(null)
    try {
      const { client, share_token } = await createProspectAction({
        name,
        website,
        industry,
        competitor,
      })
      setCreatedClient(client)
      setToken(share_token)
      toast.success("Prospect created — scan is running")
    } catch {
      setError("Failed to create prospect. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  async function handleCopy() {
    if (!url) return
    const ok = await copyToClipboard(url)
    toast[ok ? "success" : "error"](
      ok ? "Link copied to clipboard" : "Couldn't copy — copy the link manually.",
    )
  }

  function goToClient() {
    if (!createdClient) return
    onClose()
    router.push(`/clients/${createdClient.id}`)
    router.refresh()
  }

  // ── Success state: show the sendable link ──────────────────────────────────
  if (createdClient && token) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border bg-muted/40 p-3">
          <p className="text-sm font-medium">{createdClient.name}</p>
          <p className="text-xs text-muted-foreground">{createdClient.website}</p>
        </div>
        <p className="text-sm text-muted-foreground">
          The scan is running now — it&apos;ll take a few minutes. Open this
          read-only view to screen-share on your call once the scan finishes.
        </p>
        <div className="flex gap-2">
          <Input readOnly value={url ?? ""} className="font-mono text-xs" />
          <Button type="button" variant="outline" size="icon" onClick={handleCopy} title="Copy link">
            <Copy className="h-4 w-4" />
          </Button>
          <Button type="button" variant="outline" size="icon" asChild title="Open view">
            <a href={url ?? "#"} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Done
          </Button>
          <Button type="button" onClick={goToClient}>
            View prospect
          </Button>
        </div>
      </div>
    )
  }

  // ── Form state ──────────────────────────────────────────────────────────────
  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Quick scan for a lead — just the basics. You can add competitors and
        full profile details later if they sign.
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
          Add one to include the head-to-head comparison in the scan — the gap
          to show on the call.
        </p>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading}>
          {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Create &amp; scan
        </Button>
      </div>
    </form>
  )
}
