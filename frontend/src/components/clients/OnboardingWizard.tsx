// frontend/src/components/clients/OnboardingWizard.tsx
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  createClientAction,
  addCompetitorAction,
  deleteCompetitorAction,
} from "@/app/clients/actions"
import { updateClientAction } from "@/app/clients/[id]/settings/actions"
import type { Client, Competitor } from "@/types"

type Step = 1 | 2 | 3

interface Props {
  onClose: () => void
}

const INDUSTRIES = [
  "Technology", "SaaS", "E-commerce", "Healthcare", "Finance",
  "Education", "Real Estate", "Food & Beverage", "Retail", "Other",
]

export function OnboardingWizard({ onClose }: Props) {
  const router = useRouter()
  const [step, setStep] = useState<Step>(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Step 1
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [industry, setIndustry] = useState("")
  const [createdClient, setCreatedClient] = useState<Client | null>(null)

  // Step 2
  const [competitors, setCompetitors] = useState<Competitor[]>([])
  const [compName, setCompName] = useState("")
  const [compWebsite, setCompWebsite] = useState("")
  const [addingComp, setAddingComp] = useState(false)

  // Step 3
  const [description, setDescription] = useState("")
  const [targetAudience, setTargetAudience] = useState("")
  const [city, setCity] = useState("")
  const [state, setState] = useState("")
  const [contactEmail, setContactEmail] = useState("")

  function navigateToClient(client: Client) {
    onClose()
    router.push(`/clients/${client.id}`)
    router.refresh()
  }

  // ── Step 1 ──────────────────────────────────────────────────────────────────
  async function handleStep1(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const client = await createClientAction({ name, website, industry })
      setCreatedClient(client)
      setStep(2)
    } catch {
      setError("Failed to create client. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2 ──────────────────────────────────────────────────────────────────
  async function handleAddCompetitor() {
    if (!createdClient || !compName.trim()) return
    setAddingComp(true)
    setError(null)
    try {
      const comp = await addCompetitorAction(createdClient.id, {
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

  async function handleRemoveCompetitor(id: string) {
    if (!createdClient) return
    try {
      await deleteCompetitorAction(createdClient.id, id)
      setCompetitors((prev) => prev.filter((c) => c.id !== id))
    } catch {
      setError("Failed to remove competitor.")
    }
  }

  // ── Step 3 ──────────────────────────────────────────────────────────────────
  async function handleStep3(e: React.FormEvent) {
    e.preventDefault()
    if (!createdClient) return
    setLoading(true)
    setError(null)
    try {
      await updateClientAction(createdClient.id, {
        description: description || undefined,
        target_audience: targetAudience || undefined,
        city: city || undefined,
        state: state || undefined,
        contact_email: contactEmail || undefined,
      })
      navigateToClient(createdClient)
    } catch {
      setError("Failed to save. You can finish this in Settings.")
      // Still navigate — client was already created
      navigateToClient(createdClient)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {([1, 2, 3] as Step[]).map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={[
                "w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold",
                s === step ? "bg-primary text-primary-foreground" : "",
                s < step ? "bg-primary/20 text-primary" : "",
                s > step ? "bg-muted text-muted-foreground" : "",
              ].join(" ")}
            >
              {s}
            </div>
            {s < 3 && (
              <div
                className={["h-px w-8", s < step ? "bg-primary/40" : "bg-muted"].join(
                  " ",
                )}
              />
            )}
          </div>
        ))}
        <span className="ml-2 text-sm text-muted-foreground">
          {step === 1 && "Brand details"}
          {step === 2 && "Competitors (optional)"}
          {step === 3 && "Profile (optional)"}
        </span>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* ── Step 1 ── */}
      {step === 1 && (
        <form onSubmit={handleStep1} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="wiz-name">Brand name *</Label>
            <Input
              id="wiz-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Corp"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-website">Website *</Label>
            <Input
              id="wiz-website"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="https://acme.com"
              type="url"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-industry">Industry *</Label>
            <select
              id="wiz-industry"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">Select industry…</option>
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Next
            </Button>
          </div>
        </form>
      )}

      {/* ── Step 2 ── */}
      {step === 2 && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Add up to 5 competitors. You can skip this and add them later in Settings.
          </p>

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
                    variant="ghost"
                    size="sm"
                    type="button"
                    onClick={() => handleRemoveCompetitor(c.id)}
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
                <Label className="text-xs">Competitor name</Label>
                <Input
                  value={compName}
                  onChange={(e) => setCompName(e.target.value)}
                  placeholder="Rival Co"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault()
                      handleAddCompetitor()
                    }
                  }}
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
                onClick={handleAddCompetitor}
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

          <Separator />
          <div className="flex justify-between">
            <Button
              variant="ghost"
              type="button"
              onClick={() => createdClient && navigateToClient(createdClient)}
            >
              Skip — go to client
            </Button>
            <Button type="button" onClick={() => setStep(3)}>
              Next
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 3 ── */}
      {step === 3 && (
        <form onSubmit={handleStep3} className="space-y-4">
          <p className="text-sm text-muted-foreground">
            These details improve scan quality and unlock the AI Readiness Toolkit.
          </p>
          <div className="space-y-2">
            <Label htmlFor="wiz-desc">Description</Label>
            <textarea
              id="wiz-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="3–5 sentences about the business…"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-audience">Target audience</Label>
            <Input
              id="wiz-audience"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="e.g. SME owners in Malaysia"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1 space-y-2">
              <Label htmlFor="wiz-city">City</Label>
              <Input
                id="wiz-city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Kuala Lumpur"
              />
            </div>
            <div className="flex-1 space-y-2">
              <Label htmlFor="wiz-state">State</Label>
              <Input
                id="wiz-state"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="Selangor"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-email">Contact email</Label>
            <Input
              id="wiz-email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              placeholder="client@example.com"
              type="email"
            />
          </div>
          <Separator />
          <div className="flex justify-between">
            <Button
              variant="ghost"
              type="button"
              onClick={() => createdClient && navigateToClient(createdClient)}
            >
              Skip — go to client
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Finish
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}
