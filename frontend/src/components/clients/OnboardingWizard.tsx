// frontend/src/components/clients/OnboardingWizard.tsx
"use client"

import { useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { Country, State } from "country-state-city"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { SearchableSelect } from "@/components/ui/searchable-select"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  createClientAction,
  addCompetitorAction,
} from "@/app/clients/actions"
import { updateClientAction } from "@/app/clients/[id]/settings/actions"
import { INDUSTRIES } from "@/lib/industries"
import { isValidWebsite } from "@/lib/utils"
import type { Client } from "@/types"

type Step = 1 | 2 | 3

// Competitors are collected locally and only persisted once the client is
// created at the final step, so they carry a temporary client-side id.
type DraftCompetitor = { id: string; name: string; website: string }

// Mirrors the backend's contact_email rule (schemas/client.py). The browser's
// type="email" is looser (it accepts "name@localhost"), so we re-check here to
// catch a rejection before the client record is created — otherwise the client
// is created, the profile PATCH 422s, and a retry would make a duplicate.
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

interface Props {
  onClose: () => void
}

export function OnboardingWizard({ onClose }: Props) {
  const router = useRouter()
  const [step, setStep] = useState<Step>(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Holds the client once it's been created so a follow-up failure (bad profile
  // field, transient error) can be retried without creating a second client.
  const createdRef = useRef<Client | null>(null)

  // Step 1
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [industry, setIndustry] = useState("")

  // Step 2
  const [competitors, setCompetitors] = useState<DraftCompetitor[]>([])
  const [compName, setCompName] = useState("")
  const [compWebsite, setCompWebsite] = useState("")

  // Step 3
  const [description, setDescription] = useState("")
  const [targetAudience, setTargetAudience] = useState("")
  const [country, setCountry] = useState("")
  const [city, setCity] = useState("")
  const [state, setState] = useState("")
  const [contactEmail, setContactEmail] = useState("")

  const countryNames = useMemo(() => Country.getAllCountries().map((c) => c.name), [])
  const stateNames = useMemo(() => {
    const iso = Country.getAllCountries().find((c) => c.name === country)?.isoCode
    if (!iso) return []
    return State.getStatesOfCountry(iso).map((s) => s.name)
  }, [country])

  function navigateToClient(client: Client) {
    onClose()
    router.push(`/clients/${client.id}`)
    router.refresh()
  }

  // Persist everything collected across all steps in one shot. The client is
  // created here — not before — so abandoning the wizard leaves nothing behind.
  // Used by both "Finish" and the "Skip" shortcuts.
  async function createAndNavigate() {
    // Catch a backend-invalid email here, before anything is created — the
    // browser's type="email" lets "name@localhost" through but the API rejects
    // it, which would otherwise strand a created client behind a failed PATCH.
    if (contactEmail && !EMAIL_PATTERN.test(contactEmail)) {
      setStep(3) // the email field lives on step 3 — surface it
      setError("Please enter a valid contact email (e.g. name@company.com).")
      return
    }
    setLoading(true)
    setError(null)
    try {
      // Reuse the client if a previous attempt already created it, so retrying a
      // failed profile/competitor step can't leave a duplicate behind.
      const client =
        createdRef.current ?? (await createClientAction({ name, website, industry }))
      createdRef.current = client

      const profile = {
        description: description || undefined,
        target_audience: targetAudience || undefined,
        country: country || undefined,
        city: city || undefined,
        state: state || undefined,
        contact_email: contactEmail || undefined,
      }
      if (Object.values(profile).some((v) => v !== undefined)) {
        await updateClientAction(client.id, profile)
      }

      for (const c of competitors) {
        try {
          await addCompetitorAction(client.id, {
            name: c.name,
            website: c.website || undefined,
          })
        } catch {
          // Best-effort — a single failed competitor shouldn't block the client
          // (they can be re-added in Settings).
        }
      }

      navigateToClient(client) // unmounts; no need to clear loading
    } catch {
      // Distinguish the two failure modes: if the client already exists, only
      // the profile/competitor save failed — retrying reuses it (no duplicate).
      setError(
        createdRef.current
          ? "The client was created, but saving the extra details failed. Fix any invalid field and try again, or skip them."
          : "Failed to create client. Please try again.",
      )
      setLoading(false)
    }
  }

  // ── Step 1 ──────────────────────────────────────────────────────────────────
  function handleStep1(e: React.FormEvent) {
    e.preventDefault()
    if (!industry) {
      setError("Please select an industry.")
      return
    }
    if (website) {
      try {
        new URL(website)
      } catch {
        setError("Please enter a valid website URL (e.g. https://example.com).")
        return
      }
    }
    setError(null)
    setStep(2)
  }

  // ── Step 2 ──────────────────────────────────────────────────────────────────
  // Competitors are buffered locally and only written when the client is created.
  function handleAddCompetitor(): boolean {
    const trimmed = compName.trim()
    if (!trimmed) return false
    if (competitors.length >= 5) return false
    if (compWebsite.trim() && !isValidWebsite(compWebsite)) {
      setError("Enter a valid competitor website (e.g. rival.com) or leave it blank.")
      return false
    }
    setError(null)
    setCompetitors((prev) => [
      ...prev,
      { id: crypto.randomUUID(), name: trimmed, website: compWebsite.trim() },
    ])
    setCompName("")
    setCompWebsite("")
    return true
  }

  function handleStep2Next() {
    // A competitor typed into the fields but never added with "+" would be
    // silently lost — add it before moving on.
    if (compName.trim()) handleAddCompetitor()
    setStep(3)
  }

  function handleRemoveCompetitor(id: string) {
    setCompetitors((prev) => prev.filter((c) => c.id !== id))
  }

  // ── Step 3 ──────────────────────────────────────────────────────────────────
  function handleStep3(e: React.FormEvent) {
    e.preventDefault()
    createAndNavigate()
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
            <Select value={industry} onValueChange={setIndustry}>
              <SelectTrigger id="wiz-industry">
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
                disabled={!compName.trim()}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          )}

          <Separator />
          <div className="flex justify-between">
            <Button
              variant="ghost"
              type="button"
              onClick={createAndNavigate}
              disabled={loading}
            >
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Skip (create client)
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setStep(1)}>
                Previous
              </Button>
              <Button type="button" onClick={handleStep2Next}>
                Next
              </Button>
            </div>
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
          <div className="space-y-2">
            <Label htmlFor="wiz-country">Country</Label>
            <SearchableSelect
              id="wiz-country"
              options={countryNames}
              value={country}
              onChange={(next) => {
                setCountry(next)
                if (next !== country) setState("") // states list changes with country
              }}
              placeholder="Type to search… e.g. Malaysia"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1 space-y-2">
              <Label htmlFor="wiz-state">State</Label>
              {stateNames.length > 0 ? (
                <SearchableSelect
                  id="wiz-state"
                  options={stateNames}
                  value={state}
                  onChange={setState}
                  placeholder="Type to search… e.g. Selangor"
                  allowFreeText
                />
              ) : (
                <Input
                  id="wiz-state"
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                  placeholder={country ? "State / region" : "Pick a country first"}
                />
              )}
            </div>
            <div className="flex-1 space-y-2">
              <Label htmlFor="wiz-city">City</Label>
              <Input
                id="wiz-city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Kuala Lumpur"
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
              onClick={createAndNavigate}
              disabled={loading}
            >
              Skip extras
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setStep(2)}>
                Previous
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Finish
              </Button>
            </div>
          </div>
        </form>
      )}
    </div>
  )
}
