"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { PRODUCT_LANGUAGE } from "@/lib/product-language"
import type {
  AssessmentCriterion, AssessmentDimension, DimensionAssessment, DimensionReviewStatus,
} from "@/types"
import { acceptAssessmentAction, assessmentStatusAction, generateAssessmentAction } from "./actions"

// Mirror ASSESSMENT_MIN_REASON_CHARS / ASSESSMENT_MAX_BULLETS / ASSESSMENT_REVIEW_DAYS
// in backend/app/core/constants.py; the API enforces the first two.
const MIN_REASON_CHARS = 10
const MAX_BULLETS = 6
const REVIEW_DAYS = 90

const LABELS: Record<AssessmentDimension, string> = {
  brand_authority: "Brand Authority",
  content_quality: "Content Quality",
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-MY", { day: "numeric", month: "short", year: "numeric" })
}

const BASIS_LABELS: Record<string, string> = {
  measured: "Measured",
  recorded: "Recorded",
  judged: "Researched",
}

function bulletsFrom(text: string): string[] {
  return text.split("\n").map((line) => line.replace(/^[-•*]\s*/, "").trim()).filter(Boolean)
}

/**
 * Brand Authority and Content Quality are Claude-suggested and admin-reviewed.
 * This is the only place their scores change: the general settings save no
 * longer accepts them. Any change to the suggested score or evidence needs a
 * written reason, and the reviewer is recorded.
 */
export function ScoreReviewCard({
  clientId, initialStatus,
}: { clientId: string; initialStatus: DimensionReviewStatus[] }) {
  const [status, setStatus] = useState(initialStatus)

  async function refresh() {
    try { setStatus(await assessmentStatusAction(clientId)) } catch { /* keep last */ }
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold tracking-tight">Reviewed scores</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Brand Authority and Content Quality make up 40% of {PRODUCT_LANGUAGE.readiness}. Generate a
          suggestion, check the evidence, then save it as is or change it with a reason. Reviews older
          than {REVIEW_DAYS} days are flagged as due.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {status.map((item) => (
          <DimensionReview key={item.dimension} clientId={clientId} item={item} onSaved={refresh} />
        ))}
      </div>
    </section>
  )
}

function DimensionReview({
  clientId, item, onSaved,
}: { clientId: string; item: DimensionReviewStatus; onSaved: () => Promise<void> }) {
  const [draft, setDraft] = useState<DimensionAssessment | null>(null)
  const [score, setScore] = useState("")
  const [points, setPoints] = useState<Record<string, string>>({})
  const [evidence, setEvidence] = useState("")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const anchor = item.dimension === "brand_authority" ? "brand-authority" : "content-quality"

  async function generate() {
    setBusy(true)
    setError(null)
    try {
      const suggestion = await generateAssessmentAction(clientId, item.dimension)
      setDraft(suggestion)
      setScore(String(suggestion.suggested_score))
      setPoints(Object.fromEntries((suggestion.criteria ?? []).map((c) => [c.key, String(c.points)])))
      setEvidence(suggestion.evidence_bullets.join("\n"))
      setReason("")
    } catch {
      setError("The assessment failed. Try again in a moment.")
    } finally {
      setBusy(false)
    }
  }

  const checklist: AssessmentCriterion[] = draft?.criteria ?? []
  const pointValue = (c: AssessmentCriterion) => Number(points[c.key] ?? c.points)
  const checklistTotal = checklist.reduce((sum, c) => sum + (Number.isFinite(pointValue(c)) ? pointValue(c) : 0), 0)

  async function save() {
    if (!draft) return
    let n = Number(score)
    let pointsChanged = false
    if (checklist.length > 0) {
      for (const c of checklist) {
        const p = pointValue(c)
        if (!Number.isInteger(p) || p < 0 || p > c.max) {
          setError(`${c.label}: enter a whole number from 0 to ${c.max}.`)
          return
        }
        if (p !== c.points) pointsChanged = true
      }
      n = checklistTotal
    } else if (score.trim() === "" || !Number.isInteger(n) || n < 0 || n > 100) {
      setError("Enter a whole number from 0 to 100.")
      return
    }
    const bullets = bulletsFrom(evidence)
    if (bullets.length === 0) {
      setError("Keep at least one evidence point.")
      return
    }
    if (bullets.length > MAX_BULLETS) {
      setError(`Keep it to ${MAX_BULLETS} evidence points or fewer.`)
      return
    }
    const changed =
      pointsChanged || n !== draft.suggested_score
      || bullets.join("\n") !== draft.evidence_bullets.join("\n")
    if (changed && reason.trim().length < MIN_REASON_CHARS) {
      setError(`You changed the suggestion. Say why (at least ${MIN_REASON_CHARS} characters).`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await acceptAssessmentAction(clientId, item.dimension, {
        finalScore: checklist.length > 0 ? null : n,
        points: checklist.length > 0
          ? Object.fromEntries(checklist.map((c) => [c.key, pointValue(c)]))
          : null,
        bullets,
        reason: changed ? reason.trim() : null,
      })
      setDraft(null)
      await onSaved()
    } catch {
      setError("Could not save the review. Check the reason and try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div id={anchor} className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{LABELS[item.dimension]}</p>
          <p className="text-2xl font-semibold tabular-nums">{item.score ?? 0}</p>
        </div>
        {item.review_due && (
          <Badge variant="outline" className="border-amber-500/50 text-amber-600">
            {item.due_reason === "stale"
              ? "Review due"
              : item.due_reason === "method_changed" ? "Re-review: new checklist" : "Not yet reviewed"}
          </Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {item.reviewed_at
          ? `Reviewed ${formatDate(item.reviewed_at)}${item.reviewed_by ? ` by ${item.reviewed_by}` : ""}`
          : "Never reviewed. Clients see “Not yet reviewed” next to this score."}
      </p>
      {item.evidence.length > 0 && (
        <ul className="ml-4 list-disc space-y-0.5 text-xs text-muted-foreground">
          {item.evidence.map((line) => <li key={line}>{line}</li>)}
        </ul>
      )}
      {item.criteria && item.criteria.length > 0 && (
        <ul className="space-y-0.5 text-xs">
          {item.criteria.map((c) => (
            <li key={c.key} className="flex justify-between gap-2">
              <span className="text-muted-foreground">{c.label}</span>
              <span className="tabular-nums">{c.final_points ?? c.points}/{c.max}</span>
            </li>
          ))}
        </ul>
      )}
      {item.adjustment_reason && (
        <p className="text-xs text-muted-foreground">Changed from the suggestion: {item.adjustment_reason}</p>
      )}

      {!draft ? (
        <Button type="button" variant="outline" size="sm" onClick={generate} disabled={busy}>
          {busy ? "Assessing…" : item.reviewed_at ? "Review again" : "Generate assessment"}
        </Button>
      ) : (
        <div className="space-y-2 rounded-md border bg-muted/20 p-3 text-sm">
          <p className="font-medium">
            Suggested: {draft.suggested_score}
            {checklist.length > 0 && checklistTotal !== draft.suggested_score && (
              <span className="font-normal text-muted-foreground"> · your total: {checklistTotal}</span>
            )}
          </p>
          {checklist.length > 0 ? (
            <ul className="divide-y rounded-md border bg-background">
              {checklist.map((c) => (
                <li key={c.key} className="space-y-1 px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{c.label}</span>
                    <span className="flex items-center gap-1.5">
                      <Badge variant="outline">{BASIS_LABELS[c.basis] ?? c.basis}</Badge>
                      <Input
                        aria-label={`${c.label} points`} className="h-8 w-16" inputMode="numeric"
                        value={points[c.key] ?? String(c.points)}
                        onChange={(e) => setPoints((prev) => ({ ...prev, [c.key]: e.target.value }))}
                      />
                      <span className="text-xs text-muted-foreground">/ {c.max}</span>
                    </span>
                  </div>
                  {c.evidence && <p className="text-xs text-muted-foreground">{c.evidence}</p>}
                  {c.admin_hint && <p className="text-xs text-amber-700 dark:text-amber-400">{c.admin_hint}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <div className="space-y-1">
              <Label htmlFor={`${anchor}-score`}>Score (0–100)</Label>
              <Input
                id={`${anchor}-score`} className="w-24" inputMode="numeric"
                value={score} onChange={(e) => setScore(e.target.value)}
              />
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor={`${anchor}-evidence`}>Evidence shown to the client (one point per line)</Label>
            <Textarea
              id={`${anchor}-evidence`} rows={5}
              value={evidence} onChange={(e) => setEvidence(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Delete anything you could not confirm. Lines starting &ldquo;To verify&rdquo; should be
              checked or removed before you save.
            </p>
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${anchor}-reason`}>Reason for any change (internal)</Label>
            <Textarea
              id={`${anchor}-reason`} rows={2}
              placeholder="Required if you change the score or the evidence"
              value={reason} onChange={(e) => setReason(e.target.value)}
            />
          </div>
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Button type="button" size="sm" onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save review"}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(null)} disabled={busy}>
              Discard
            </Button>
          </div>
        </div>
      )}
      {!draft && error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
