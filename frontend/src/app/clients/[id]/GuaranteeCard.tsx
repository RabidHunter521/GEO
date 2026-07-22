// frontend/src/app/clients/[id]/GuaranteeCard.tsx
// Admin guarantee widget: create a commitment, watch pace, resolve outcome.
// States are derived server-side; terminal outcomes are admin-gated.
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Loader2, ShieldCheck } from "lucide-react"
import { createGuaranteeAction, resolveGuaranteeAction } from "@/app/clients/actions"
import type { GuaranteeProgress } from "@/types"

const STATE_STYLE: Record<GuaranteeProgress["state"], { label: string; cls: string }> = {
  met:             { label: "Target met",     cls: "border-score-strong/40 bg-score-strong-bg text-score-strong" },
  on_track:        { label: "On track",       cls: "border-score-strong/40 bg-score-strong-bg text-score-strong" },
  at_risk:         { label: "Behind pace",    cls: "border-score-watch/40 bg-score-watch-bg text-score-watch" },
  deadline_passed: { label: "Deadline passed", cls: "border-destructive/40 bg-destructive/10 text-destructive" },
}

function ProgressBar({ baseline, target, current }: { baseline: number; target: number; current: number | null }) {
  const span = Math.max(target - baseline, 1)
  const pct = current === null ? 0 : Math.max(0, Math.min(100, ((current - baseline) / span) * 100))
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
    </div>
  )
}

export function GuaranteeCard({
  clientId,
  initialProgress,
}: {
  clientId: string
  initialProgress: GuaranteeProgress | null
}) {
  const [progress, setProgress] = useState<GuaranteeProgress | null>(initialProgress)
  const [target, setTarget] = useState("")
  const [deadline, setDeadline] = useState("")
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    const t = Number(target)
    if (!Number.isFinite(t) || t < 1 || t > 100 || !deadline) {
      setError("Enter a target (1–100) and a deadline date.")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const p = await createGuaranteeAction(clientId, { target_value: t, deadline_date: deadline })
      setProgress(p)
      setTarget("")
      setDeadline("")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create the commitment.")
    } finally {
      setBusy(false)
    }
  }

  async function handleResolve(outcome: "met" | "missed" | "void") {
    if (!progress) return
    setBusy(true)
    setError(null)
    try {
      await resolveGuaranteeAction(clientId, progress.id, outcome, note.trim() || undefined)
      setProgress(null)
      setNote("")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resolve the commitment.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <ShieldCheck className="h-4 w-4 text-primary" />
        Visibility commitment
      </p>

      {progress ? (
        <div className="mt-3 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {progress.metric === "ai_citability" ? "AI visibility" : "Overall score"}{" "}
              <span className="font-semibold text-foreground">{progress.baseline_value}</span>
              {" → "}
              <span className="font-semibold text-foreground">{progress.target_value}</span>{" "}
              by{" "}
              {new Date(progress.deadline_date).toLocaleDateString("en-MY", {
                day: "numeric", month: "short", year: "numeric",
              })}
            </p>
            <Badge variant="outline" className={`shrink-0 text-xs font-medium ${STATE_STYLE[progress.state].cls}`}>
              {STATE_STYLE[progress.state].label}
            </Badge>
          </div>
          <ProgressBar
            baseline={progress.baseline_value}
            target={progress.target_value}
            current={progress.current_value}
          />
          <p className="text-xs text-muted-foreground">
            Today:{" "}
            <span className="font-semibold text-foreground tabular-nums">
              {progress.current_value !== null ? progress.current_value.toFixed(1) : "—"}
            </span>
            {" · "}
            {progress.points_gained >= 0 ? "+" : ""}
            {progress.points_gained.toFixed(1)} of {progress.points_needed} points
            {" · "}
            {progress.days_remaining} days remaining
          </p>
          {progress.state === "deadline_passed" && (
            <div className="space-y-2 rounded-md border border-dashed p-3">
              <Label className="text-xs">Resolve — note (optional)</Label>
              <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. remedy agreed: one free month" />
              <div className="flex gap-2">
                <Button type="button" size="sm" disabled={busy} onClick={() => handleResolve("met")}>
                  Met
                </Button>
                <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => handleResolve("missed")}>
                  Missed
                </Button>
                <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => handleResolve("void")}>
                  Void
                </Button>
              </div>
            </div>
          )}
          {progress.state !== "deadline_passed" && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              disabled={busy}
              onClick={() => handleResolve("void")}
            >
              Void commitment
            </Button>
          )}
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">
            Commit to a visibility target. Baseline auto-fills from the latest
            scan; pace is tracked on every scan and you get alerted the moment
            it falls behind.
          </p>
          <div className="flex gap-2 items-end">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Target (AI visibility)</Label>
              <Input type="number" min="1" max="100" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="60" />
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Deadline</Label>
              <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </div>
            <Button type="button" variant="outline" disabled={busy || !target || !deadline} onClick={handleCreate}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Commit"}
            </Button>
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  )
}
