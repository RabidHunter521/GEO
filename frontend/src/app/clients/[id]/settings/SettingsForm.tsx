// frontend/src/app/clients/[id]/settings/SettingsForm.tsx
"use client"

import { useState, useTransition, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Loader2, CheckCircle, Plus, Trash2, HelpCircle, Lightbulb } from "lucide-react"
import { updateClientAction, updateTrafficAction, uploadClientLogoAction, syncGa4TrafficAction } from "./actions"
import {
  addCompetitorAction,
  addControlQueryAction,
  deleteCompetitorAction,
  toggleControlQueryAction,
} from "@/app/clients/actions"
import type { Client, Competitor, ControlQuery, AiTrafficSnapshot, Platform, DimensionAssessment, AssessmentDimension } from "@/types"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"
import { industryOptions } from "@/lib/industries"
import { isValidWebsite } from "@/lib/utils"
import { generateAssessment, acceptAssessment } from "@/lib/api"

interface Props {
  client: Client
  competitors: Competitor[]
  contentRecommendation?: string | null
  trafficHistory: AiTrafficSnapshot[]
  controlQueries: ControlQuery[]
}

function currentMonthPeriod(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`
}

function formatPeriod(period: string): string {
  return new Date(period).toLocaleDateString("en-MY", { month: "long", year: "numeric" })
}

function AssessmentReview({
  clientId,
  dimension,
  onAccepted,
}: {
  clientId: string;
  dimension: AssessmentDimension;
  onAccepted: (score: number) => void;
}) {
  const [draft, setDraft] = useState<DimensionAssessment | null>(null)
  const [loading, setLoading] = useState(false)
  const [adjust, setAdjust] = useState<string>("")

  async function generate() {
    setLoading(true)
    try {
      const a = await generateAssessment(clientId, dimension)
      setDraft(a)
      setAdjust(String(a.suggested_score))
    } catch {
      alert("Assessment failed — please try again.")
    } finally {
      setLoading(false)
    }
  }

  async function accept(useAdjusted: boolean) {
    if (!draft) return
    let finalScore: number | null = null
    if (useAdjusted) {
      const n = Number(adjust)
      if (adjust === "" || Number.isNaN(n) || n < 0 || n > 100) {
        alert("Enter a score between 0 and 100.")
        return
      }
      finalScore = n
    }
    try {
      const saved = await acceptAssessment(clientId, dimension, finalScore)
      onAccepted(saved.final_score ?? saved.suggested_score)
      setDraft(null)
    } catch {
      alert("Could not save the assessment — please try again.")
    }
  }

  return (
    <div className="mt-2">
      <Button type="button" variant="outline" size="sm" onClick={generate} disabled={loading}>
        {loading ? "Assessing…" : "Generate assessment"}
      </Button>
      {draft && (
        <div className="mt-2 rounded-md border p-3 text-sm">
          <div className="font-medium">Suggested: {draft.suggested_score}</div>
          <ul className="ml-4 list-disc">
            {draft.evidence_bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2">
            <Button type="button" size="sm" onClick={() => accept(false)}>
              Accept
            </Button>
            <Input
              className="w-16"
              value={adjust}
              onChange={(e) => setAdjust(e.target.value)}
            />
            <Button type="button" size="sm" variant="secondary" onClick={() => accept(true)}>
              Adjust &amp; accept
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export function SettingsForm({ client, competitors: initialCompetitors, contentRecommendation, trafficHistory, controlQueries: initialControlQueries }: Props) {
  const [isPending, startTransition] = useTransition()
  const [saved, setSaved] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [platformWarning, setPlatformWarning] = useState(false)

  useEffect(() => {
    if (!isDirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [isDirty])
  const [competitors, setCompetitors] = useState<Competitor[]>(initialCompetitors)
  const [compName, setCompName] = useState("")
  const [compWebsite, setCompWebsite] = useState("")
  const [addingComp, setAddingComp] = useState(false)

  const [controlQueries, setControlQueries] = useState<ControlQuery[]>(initialControlQueries)
  const [controlText, setControlText] = useState("")
  const [addingControl, setAddingControl] = useState(false)
  const [controlError, setControlError] = useState<string | null>(null)

  const [enabledPlatforms, setEnabledPlatforms] = useState<Platform[]>(
    () => client.enabled_platforms?.length ? client.enabled_platforms : [...SCAN_PLATFORMS]
  )

  function togglePlatform(platform: Platform) {
    setEnabledPlatforms((prev) => {
      if (prev.includes(platform)) {
        if (prev.length === 1) {
          setPlatformWarning(true)
          return prev
        }
        setPlatformWarning(false)
        return prev.filter((p) => p !== platform)
      }
      setPlatformWarning(false)
      return SCAN_PLATFORMS.filter((p) => prev.includes(p) || p === platform)
    })
    setIsDirty(true)
  }

  const [brandAuthorityScore, setBrandAuthorityScore] = useState<string>(
    client.brand_authority_score != null ? String(client.brand_authority_score) : ""
  )
  const [contentQualityScore, setContentQualityScore] = useState<string>(
    client.content_quality_score != null ? String(client.content_quality_score) : ""
  )

  const [logoUrl, setLogoUrl] = useState<string | null>(client.logo_url)
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const logoInputRef = useRef<HTMLInputElement>(null)

  async function handleLogoSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = "" // allow re-selecting the same file later
    if (!file) return
    if (file.size > 2 * 1024 * 1024) {
      setLogoError("Image too large (max 2 MB).")
      return
    }
    setLogoError(null)
    setUploadingLogo(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const updated = await uploadClientLogoAction(client.id, fd)
      setLogoUrl(updated.logo_url)
    } catch (err) {
      setLogoError(err instanceof Error ? err.message : "Logo upload failed.")
    } finally {
      setUploadingLogo(false)
    }
  }

  async function handleLogoRemove() {
    setLogoError(null)
    try {
      await updateClientAction(client.id, { logo_url: "" })
      setLogoUrl(null)
    } catch {
      setLogoError("Failed to remove logo.")
    }
  }

  const currentPeriod = currentMonthPeriod()
  const [traffic, setTraffic] = useState<AiTrafficSnapshot[]>(trafficHistory)
  const currentTrafficValue = traffic.find((t) => t.period.slice(0, 10) === currentPeriod)?.ai_visitors
  const [trafficInput, setTrafficInput] = useState(currentTrafficValue?.toString() ?? "")
  const [savingTraffic, setSavingTraffic] = useState(false)
  const [trafficError, setTrafficError] = useState<string | null>(null)
  const [syncingGa4, setSyncingGa4] = useState(false)
  const [ga4Result, setGa4Result] = useState<string | null>(null)

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setError(null)
    setSaved(false)

    // A manual dimension score must never appear "naked" to the client — require
    // an evidence line whenever a score is set above 0 (mirrors the backend rule).
    const baScore = Number(fd.get("brand_authority_score") || 0)
    const baEvidence = ((fd.get("brand_authority_evidence") as string) || "").trim()
    if (baScore > 0 && !baEvidence) {
      setError("Add a short evidence note for the Brand Authority score — it must never appear to the client without a reason.")
      return
    }
    const cqScore = Number(fd.get("content_quality_score") || 0)
    const cqEvidence = ((fd.get("content_quality_evidence") as string) || "").trim()
    if (cqScore > 0 && !cqEvidence) {
      setError("Add a short evidence note for the Content Quality score — it must never appear to the client without a reason.")
      return
    }

    const dealRaw = (fd.get("avg_deal_value_rm") as string) ?? ""
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
          country: (fd.get("country") as string) || undefined,
          phone: (fd.get("phone") as string) || undefined,
          contact_email: (fd.get("contact_email") as string) || undefined,
          brand_authority_score: fd.get("brand_authority_score")
            ? Number(fd.get("brand_authority_score"))
            : undefined,
          brand_authority_evidence: (fd.get("brand_authority_evidence") as string) || undefined,
          content_quality_score: fd.get("content_quality_score")
            ? Number(fd.get("content_quality_score"))
            : undefined,
          content_quality_evidence: (fd.get("content_quality_evidence") as string) || undefined,
          score_drop_threshold: fd.get("score_drop_threshold")
            ? Number(fd.get("score_drop_threshold"))
            : undefined,
          scan_cadence_days: fd.get("scan_cadence_days")
            ? Number(fd.get("scan_cadence_days"))
            : undefined,
          // Empty deal value clears it (null); presence sets it. Conversion
          // percentages always send a number (default to current).
          avg_deal_value_rm: dealRaw.trim() === "" ? null : Number(dealRaw),
          visitor_to_lead_pct: fd.get("visitor_to_lead_pct")
            ? Number(fd.get("visitor_to_lead_pct"))
            : undefined,
          lead_to_customer_pct: fd.get("lead_to_customer_pct")
            ? Number(fd.get("lead_to_customer_pct"))
            : undefined,
          enabled_platforms: enabledPlatforms,
          // Empty property id clears it (back to manual mode).
          ga4_property_id: ((fd.get("ga4_property_id") as string) ?? "").trim() || null,
        })
        setSaved(true)
        setIsDirty(false)
      } catch (err) {
        // Surface the backend's specific message (e.g. the evidence rule) instead
        // of a generic failure when one is available.
        setError(err instanceof Error ? err.message : "Failed to save. Please try again.")
      }
    })
  }

  async function handleAddComp() {
    if (!compName.trim()) return
    if (compWebsite.trim() && !isValidWebsite(compWebsite)) {
      setError("Enter a valid competitor website (e.g. rival.com) or leave it blank.")
      return
    }
    setError(null)
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

  async function handleSyncGa4() {
    setSyncingGa4(true)
    setGa4Result(null)
    try {
      const report = await syncGa4TrafficAction(client.id)
      if (report.error) {
        setGa4Result(`Sync failed: ${report.error}`)
      } else {
        const fmt = (p: string) =>
          new Date(p).toLocaleDateString("en-MY", { month: "short", year: "numeric" })
        const synced = report.synced_periods.map(fmt).join(", ") || "nothing new"
        const skipped = report.skipped_manual.length
          ? ` · kept manual: ${report.skipped_manual.map(fmt).join(", ")}`
          : ""
        setGa4Result(`Synced: ${synced}${skipped}`)
      }
    } catch {
      setGa4Result("Sync failed — check the backend logs.")
    } finally {
      setSyncingGa4(false)
    }
  }

  async function handleSaveTraffic() {
    const visitors = Number(trafficInput)
    if (!Number.isFinite(visitors) || visitors < 0) {
      setTrafficError("Enter a whole number of visitors (0 or more).")
      return
    }
    setTrafficError(null)
    setSavingTraffic(true)
    try {
      const snapshot = await updateTrafficAction(client.id, currentPeriod, visitors)
      setTraffic((prev) => [snapshot, ...prev.filter((t) => t.period.slice(0, 10) !== currentPeriod)])
    } catch {
      setError("Failed to save AI traffic.")
    } finally {
      setSavingTraffic(false)
    }
  }

  async function handleAddControl() {
    if (!controlText.trim()) return
    setControlError(null)
    setAddingControl(true)
    try {
      const cq = await addControlQueryAction(client.id, { query_text: controlText.trim() })
      setControlQueries((prev) => [...prev, cq])
      setControlText("")
    } catch (e) {
      setControlError(e instanceof Error ? e.message : "Failed to add benchmark query.")
    } finally {
      setAddingControl(false)
    }
  }

  async function handleToggleControl(cqId: string, active: boolean) {
    setControlError(null)
    try {
      const cq = await toggleControlQueryAction(client.id, cqId, active)
      setControlQueries((prev) => prev.map((q) => (q.id === cqId ? cq : q)))
    } catch (e) {
      setControlError(e instanceof Error ? e.message : "Failed to update benchmark query.")
    }
  }

  async function handleRemoveComp(compId: string) {
    try {
      await deleteCompetitorAction(client.id, compId)
      setCompetitors((prev) => prev.filter((c) => c.id !== compId))
    } catch {
      setError("Failed to remove competitor.")
    }
  }

  return (
    <form onSubmit={handleSave} onChange={() => setIsDirty(true)} className="space-y-8">
      {/* Brand details */}
      <section className="space-y-4">
        <h2 className="font-display text-lg font-semibold tracking-tight">Brand Details</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 space-y-1">
            <Label htmlFor="s-name">Brand name</Label>
            <Input id="s-name" name="name" defaultValue={client.name} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-website">Website</Label>
            <Input id="s-website" name="website" type="url" defaultValue={client.website} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-industry">Industry</Label>
            <Select name="industry" defaultValue={client.industry} onValueChange={() => setIsDirty(true)}>
              <SelectTrigger id="s-industry">
                <SelectValue placeholder="Select industry" />
              </SelectTrigger>
              <SelectContent>
                {industryOptions(client.industry).map((i) => (
                  <SelectItem key={i} value={i}>{i}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </section>

      <Separator />

      {/* Profile */}
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">Profile</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            These fields power the AI Readiness Toolkit generator — the more complete, the better the output.
          </p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-desc">Description</Label>
          <textarea
            id="s-desc"
            name="description"
            defaultValue={client.description ?? ""}
            rows={3}
            placeholder="What does this business do? What makes them different? How do they help their customers?"
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-audience">Target audience</Label>
          <Input
            id="s-audience"
            name="target_audience"
            defaultValue={client.target_audience ?? ""}
            placeholder="e.g. SME owners in Kuala Lumpur, Malaysian F&B operators"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-country">Country</Label>
          <Input id="s-country" name="country" defaultValue={client.country ?? ""} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-state">State</Label>
            <Input id="s-state" name="state" defaultValue={client.state ?? ""} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-city">City</Label>
            <Input id="s-city" name="city" defaultValue={client.city ?? ""} />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-phone">Phone</Label>
          <Input id="s-phone" name="phone" defaultValue={client.phone ?? ""} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-email">Contact email</Label>
          <Input
            id="s-email"
            name="contact_email"
            type="email"
            defaultValue={client.contact_email ?? ""}
            placeholder="e.g. hello@clientdomain.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Logo</Label>
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted/30">
              {logoUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={logoUrl} alt="Client logo" className="h-full w-full object-contain p-1" />
              ) : (
                <span className="text-[10px] text-muted-foreground">No logo</span>
              )}
            </div>
            <div className="space-y-1.5">
              <input
                ref={logoInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                onChange={handleLogoSelect}
                className="hidden"
              />
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={uploadingLogo}
                  onClick={() => logoInputRef.current?.click()}
                >
                  {uploadingLogo && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {logoUrl ? "Replace logo" : "Upload logo"}
                </Button>
                {logoUrl && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={handleLogoRemove}
                  >
                    Remove
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Shown in the client&apos;s shared view header. PNG, JPG, WEBP or GIF, up to 2&nbsp;MB.
              </p>
              {logoError && <p className="text-xs text-destructive">{logoError}</p>}
            </div>
          </div>
        </div>
      </section>

      <Separator />

      {/* Manual scores */}
      <section id="brand-authority" className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">Manual Score Inputs</h2>
          <p className="text-xs text-muted-foreground mt-0.5 italic">
            Based on public evidence · Reviewed by SeenBy
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
              value={brandAuthorityScore}
              onChange={(e) => { setBrandAuthorityScore(e.target.value); setIsDirty(true) }}
            />
            <AssessmentReview
              clientId={client.id}
              dimension="brand_authority"
              onAccepted={(score) => { setBrandAuthorityScore(String(score)); setIsDirty(true) }}
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
              value={contentQualityScore}
              onChange={(e) => { setContentQualityScore(e.target.value); setIsDirty(true) }}
            />
            <AssessmentReview
              clientId={client.id}
              dimension="content_quality"
              onAccepted={(score) => { setContentQualityScore(String(score)); setIsDirty(true) }}
            />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-1">
              <Label htmlFor="s-threshold">Score Drop Threshold</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <button type="button" className="text-muted-foreground hover:text-foreground transition-colors">
                    <HelpCircle className="h-3.5 w-3.5" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-64 text-sm">
                  Alert fires when the overall GEO score drops below this number. Set to 0 to disable.
                </PopoverContent>
              </Popover>
            </div>
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
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-1">
              <Label htmlFor="s-cadence">Review cadence (days)</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <button type="button" className="text-muted-foreground hover:text-foreground transition-colors">
                    <HelpCircle className="h-3.5 w-3.5" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-64 text-sm">
                  How many days between recommended scans. The client card on the dashboard will flag a &quot;Scan due&quot; reminder when this period has passed since the last scan. Nothing auto-scans — all scans are triggered manually.
                </PopoverContent>
              </Popover>
            </div>
            <Input
              id="s-cadence"
              name="scan_cadence_days"
              type="number"
              min="1"
              max="365"
              step="1"
              defaultValue={client.scan_cadence_days}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-authority-evidence">
              Brand Authority — why this score?{" "}
              <span className="text-muted-foreground">(required when score &gt; 0)</span>
            </Label>
            <Textarea
              id="s-authority-evidence"
              name="brand_authority_evidence"
              rows={3}
              placeholder="e.g. 150 Google reviews, featured in The Star, active LinkedIn page"
              defaultValue={client.brand_authority_evidence ?? ""}
            />
            <p className="text-xs text-muted-foreground">
              Shown to the client under &ldquo;Based on public evidence · Reviewed by SeenBy&rdquo; — never leave it blank with a score set.
            </p>
          </div>
          <div id="content-quality" className="space-y-1">
            <Label htmlFor="s-content-evidence">
              Content Quality — why this score?{" "}
              <span className="text-muted-foreground">(required when score &gt; 0)</span>
            </Label>
            <Textarea
              id="s-content-evidence"
              name="content_quality_evidence"
              rows={3}
              placeholder="e.g. Blog publishes weekly, FAQ page present, thin product descriptions"
              defaultValue={client.content_quality_evidence ?? ""}
            />
            <p className="text-xs text-muted-foreground">
              Shown to the client under &ldquo;Based on public evidence · Reviewed by SeenBy&rdquo; — never leave it blank with a score set.
            </p>
          </div>
        </div>

        {contentRecommendation && (
          <div className="rounded-md border bg-muted/10 px-4 py-3 flex gap-3">
            <Lightbulb className="h-4 w-4 shrink-0 text-score-watch mt-0.5" />
            <div>
              <p className="text-sm font-medium">
                Content Quality suggestion{" "}
                <span className="font-normal text-muted-foreground">
                  (from the latest Content Gaps analysis — informational only)
                </span>
              </p>
              <p className="text-sm text-muted-foreground leading-relaxed mt-1">
                {contentRecommendation}
              </p>
            </div>
          </div>
        )}
      </section>

      <Separator />

      {/* Scan platforms */}
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">Scan Platforms</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            AI platforms queried on every scan. At least one must stay enabled — fewer platforms
            means lower scan cost but a narrower visibility picture.
          </p>
          {platformWarning && (
            <p className="text-xs text-destructive mt-1">
              At least one platform must stay enabled.
            </p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {SCAN_PLATFORMS.map((p) => {
            const checked = enabledPlatforms.includes(p)
            return (
              <label
                key={p}
                className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
                  checked ? "border-primary/40 bg-primary/5" : "hover:bg-muted/30"
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => togglePlatform(p)}
                  className="h-4 w-4 accent-primary"
                />
                <span className="font-medium">{PLATFORM_LABELS[p]}</span>
              </label>
            )
          })}
        </div>
      </section>

      <Separator />

      {/* Competitors */}
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">
            Competitors ({competitors.length}/5)
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Adding or removing competitors takes effect immediately — no need to save.
          </p>
        </div>
        {competitors.length > 0 && (
          <ul className="space-y-2">
            {competitors.map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-medium">{c.name ?? "Unnamed competitor"}</span>
                  {c.website && (
                    <span className="text-muted-foreground ml-2">{c.website}</span>
                  )}
                </span>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        Remove {c.name ?? "this competitor"}?
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        This also removes their data from past scan results.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => handleRemoveComp(c.id)}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      >
                        Remove
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
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
                // Competitors save on their own — don't dirty the main form.
                onChange={(e) => {
                  e.stopPropagation()
                  setCompName(e.target.value)
                }}
                placeholder="Rival Co"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Website (optional)</Label>
              <Input
                value={compWebsite}
                onChange={(e) => {
                  e.stopPropagation()
                  setCompWebsite(e.target.value)
                }}
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

      <Separator />

      {/* Benchmark queries we leave alone (causal proof) */}
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">
            Benchmark queries we leave alone ({controlQueries.filter((q) => q.active).length}/5)
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Pick queries the retainer will NOT touch. If we later work on one,
            deactivate it. They run on every scan but never affect the score —
            they exist to prove our work moved the queries we optimized.
          </p>
        </div>
        {controlQueries.length > 0 && (
          <ul className="space-y-2">
            {controlQueries.map((q) => (
              <li
                key={q.id}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
              >
                <span className={q.active ? "" : "text-muted-foreground line-through"}>
                  {q.query_text}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 shrink-0 px-2 text-xs text-muted-foreground"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleToggleControl(q.id, !q.active)
                  }}
                >
                  {q.active ? "Deactivate" : "Reactivate"}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {controlQueries.filter((q) => q.active).length < 5 && (
          <div className="flex gap-2 items-end">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Query</Label>
              <Input
                value={controlText}
                // Benchmark queries save on their own — don't dirty the main form.
                onChange={(e) => {
                  e.stopPropagation()
                  setControlText(e.target.value)
                }}
                placeholder="Best physio clinic in Penang"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={handleAddControl}
              disabled={addingControl || !controlText.trim()}
            >
              {addingControl ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
            </Button>
          </div>
        )}
        {controlError && <p className="text-xs text-destructive">{controlError}</p>}
      </section>

      <Separator />

      {/* AI Referral Traffic */}
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">AI Referral Traffic</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Monthly AI-referral visitor count from the client&apos;s analytics. Informational only — does not affect the GEO score.
          </p>
        </div>

        {/* GA4 auto-sync */}
        <div className="space-y-2 rounded-md border bg-muted/20 p-3">
          <div className="flex gap-2 items-end">
            <div className="flex-1 space-y-1">
              <Label htmlFor="s-ga4-property" className="text-xs">
                GA4 property ID (optional — enables automatic sync)
              </Label>
              <Input
                id="s-ga4-property"
                name="ga4_property_id"
                defaultValue={client.ga4_property_id ?? ""}
                placeholder="123456789"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={(e) => {
                e.stopPropagation()
                handleSyncGa4()
              }}
              disabled={syncingGa4 || !client.ga4_property_id}
            >
              {syncingGa4 ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Sync traffic"
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Grant Viewer access on the GA4 property to the SeenBy service
            account first. Save the form after changing the property ID, then
            sync. Months you typed by hand are never overwritten.
          </p>
          {ga4Result && (
            <p className={`text-xs ${ga4Result.startsWith("Sync") && ga4Result.includes("failed") ? "text-destructive" : "text-muted-foreground"}`}>
              {ga4Result}
            </p>
          )}
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1 space-y-1">
            <Label htmlFor="s-traffic">AI visitors this month ({formatPeriod(currentPeriod)})</Label>
            <Input
              id="s-traffic"
              type="number"
              min="0"
              value={trafficInput}
              // AI traffic saves on its own — don't dirty the main form.
              onChange={(e) => {
                e.stopPropagation()
                setTrafficInput(e.target.value)
                setTrafficError(null)
              }}
              placeholder="e.g. 187"
            />
            {trafficError && <p className="text-xs text-destructive">{trafficError}</p>}
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={handleSaveTraffic}
            disabled={savingTraffic || trafficInput === ""}
          >
            {savingTraffic ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
          </Button>
        </div>
        {traffic.length > 0 && (
          <ul className="space-y-1">
            {traffic.slice(0, 6).map((t) => (
              <li key={t.id} className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{formatPeriod(t.period)}</span>
                <span className="font-medium text-foreground">{t.ai_visitors.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Pipeline value inputs — turn AI visitors into the one RM number the
            client sees. Saved with the main form (Save changes below). */}
        <div className="rounded-md border bg-muted/10 p-4 space-y-3">
          <div className="flex items-center gap-1">
            <p className="text-sm font-medium">Pipeline value estimate</p>
            <Popover>
              <PopoverTrigger asChild>
                <button type="button" className="text-muted-foreground hover:text-foreground transition-colors">
                  <HelpCircle className="h-3.5 w-3.5" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-72 text-sm">
                Turns monthly AI visitors into an estimated RM pipeline on the client report:
                visitors × visitor-to-lead % × deal value = pipeline; × close rate = estimated won.
                Leave deal value blank to show visitor counts only (no RM).
              </PopoverContent>
            </Popover>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label htmlFor="s-deal-value">Avg deal value (RM)</Label>
              <Input
                id="s-deal-value"
                name="avg_deal_value_rm"
                type="number"
                min="0"
                step="1"
                placeholder="e.g. 5000"
                defaultValue={client.avg_deal_value_rm ?? ""}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="s-v2l">Visitor → lead (%)</Label>
              <Input
                id="s-v2l"
                name="visitor_to_lead_pct"
                type="number"
                min="0"
                max="100"
                step="1"
                defaultValue={client.visitor_to_lead_pct}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="s-l2c">Close rate (%)</Label>
              <Input
                id="s-l2c"
                name="lead_to_customer_pct"
                type="number"
                min="0"
                max="100"
                step="1"
                defaultValue={client.lead_to_customer_pct}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Save footer */}
      <div className="flex items-center gap-3 pt-2">
        <Button type="submit" disabled={isPending}>
          {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Save changes
        </Button>
        {saved && !isDirty && (
          <span className="flex items-center gap-1 text-sm text-score-strong">
            <CheckCircle className="h-4 w-4" />
            Saved
          </span>
        )}
        {isDirty && !isPending && (
          <span className="text-sm text-muted-foreground">Unsaved changes</span>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </form>
  )
}
