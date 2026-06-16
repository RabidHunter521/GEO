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
import { updateClientAction, updateTrafficAction, uploadClientLogoAction } from "./actions"
import {
  addCompetitorAction,
  deleteCompetitorAction,
  archiveClientAction,
} from "@/app/clients/actions"
import type { Client, Competitor, AiTrafficSnapshot, Platform } from "@/types"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"
import { industryOptions } from "@/lib/industries"

interface Props {
  client: Client
  competitors: Competitor[]
  contentRecommendation?: string | null
  trafficHistory: AiTrafficSnapshot[]
}

function currentMonthPeriod(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`
}

function formatPeriod(period: string): string {
  return new Date(period).toLocaleDateString("en-MY", { month: "long", year: "numeric" })
}

export function SettingsForm({ client, competitors: initialCompetitors, contentRecommendation, trafficHistory }: Props) {
  const [isPending, startTransition] = useTransition()
  const [saved, setSaved] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [archiving, setArchiving] = useState(false)

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

  const [enabledPlatforms, setEnabledPlatforms] = useState<Platform[]>(
    () => client.enabled_platforms?.length ? client.enabled_platforms : [...SCAN_PLATFORMS]
  )

  function togglePlatform(platform: Platform) {
    setEnabledPlatforms((prev) => {
      if (prev.includes(platform)) {
        if (prev.length === 1) return prev // at least one platform must stay enabled
        return prev.filter((p) => p !== platform)
      }
      return SCAN_PLATFORMS.filter((p) => prev.includes(p) || p === platform)
    })
    setIsDirty(true)
  }

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
          country: (fd.get("country") as string) || undefined,
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
          enabled_platforms: enabledPlatforms,
        })
        setSaved(true)
        setIsDirty(false)
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

  async function handleSaveTraffic() {
    const visitors = Number(trafficInput)
    if (!Number.isFinite(visitors) || visitors < 0) return
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

  async function handleRemoveComp(compId: string) {
    try {
      await deleteCompetitorAction(client.id, compId)
      setCompetitors((prev) => prev.filter((c) => c.id !== compId))
    } catch {
      setError("Failed to remove competitor.")
    }
  }

  async function handleArchive() {
    setArchiving(true)
    await archiveClientAction(client.id)
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
        <h2 className="font-display text-lg font-semibold tracking-tight">Profile</h2>
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
          <Label htmlFor="s-email">Contact email</Label>
          <Input
            id="s-email"
            name="contact_email"
            type="email"
            defaultValue={client.contact_email ?? ""}
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
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">Manual Score Inputs</h2>
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
              defaultValue={client.scan_cadence_days}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-authority-evidence">Brand Authority — why this score? (optional)</Label>
            <Textarea
              id="s-authority-evidence"
              name="brand_authority_evidence"
              rows={3}
              placeholder="e.g. 150 Google reviews, featured in The Star, active LinkedIn page"
              defaultValue={client.brand_authority_evidence ?? ""}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-content-evidence">Content Quality — why this score? (optional)</Label>
            <Textarea
              id="s-content-evidence"
              name="content_quality_evidence"
              rows={3}
              placeholder="e.g. Blog publishes weekly, FAQ page present, thin product descriptions"
              defaultValue={client.content_quality_evidence ?? ""}
            />
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

      {/* AI Referral Traffic */}
      <section className="space-y-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">AI Referral Traffic</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Monthly AI-referral visitor count from the client&apos;s analytics. Informational only — does not affect the GEO score.
          </p>
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
              }}
              placeholder="e.g. 187"
            />
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

      <Separator />

      {/* Danger zone */}
      <section className="space-y-3">
        <h2 className="font-display text-lg font-semibold tracking-tight text-destructive">
          Danger Zone
        </h2>
        <p className="text-sm text-muted-foreground">
          Archiving removes this client from the dashboard. All data is retained for 6 months per our retention policy.
        </p>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="outline"
              className="border-destructive/40 text-destructive hover:bg-destructive/5 hover:text-destructive"
              disabled={archiving}
            >
              {archiving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Archive client
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Archive {client.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                They will be removed from your dashboard. All data is retained for
                6 months per the retention policy, then auto-deleted.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleArchive}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Archive
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </section>
    </form>
  )
}
