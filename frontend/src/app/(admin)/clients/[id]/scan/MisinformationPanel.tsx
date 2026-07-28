// frontend/src/app/(admin)/clients/[id]/scan/MisinformationPanel.tsx
// Admin review queue for statements an AI made about the client that are wrong
// or create advertising risk. Every quote here is verbatim from a stored AI
// answer — the backend rejects any finding it cannot match word-for-word.
//
// ADMIN-ONLY. Nothing on this panel is client-visible: a finding only reaches
// the monthly report after Faris confirms it, and "candidate fixed" is a
// suggestion from a later scan, never proof on its own.
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { MisinformationFinding, MisinformationStatus } from "@/types"
import {
  reviewMisinformationAction,
  markMisinformationCorrectedAction,
  resolveMisinformationAction,
} from "./actions"

const SEVERITY_CHIP: Record<MisinformationFinding["severity"], string> = {
  high: "bg-score-low-bg text-score-low",
  medium: "bg-score-watch-bg text-score-watch",
  low: "bg-muted text-muted-foreground",
}

const STATUS_LABEL: Record<MisinformationStatus, string> = {
  suggested: "Needs review",
  confirmed: "Confirmed",
  dismissed: "Dismissed",
  corrected: "Fix submitted",
  candidate_fixed: "Looks fixed — confirm?",
  verified_fixed: "Fixed",
}

const STATUS_CHIP: Record<MisinformationStatus, string> = {
  suggested: "bg-score-watch-bg text-score-watch",
  confirmed: "bg-score-low-bg text-score-low",
  dismissed: "bg-muted text-muted-foreground",
  corrected: "bg-score-watch-bg text-score-watch",
  candidate_fixed: "bg-score-strong-bg text-score-strong",
  verified_fixed: "bg-score-strong-bg text-score-strong",
}

export function MisinformationPanel({
  clientId,
  initialFindings,
}: {
  clientId: string
  initialFindings: MisinformationFinding[]
}) {
  const [findings, setFindings] = useState<MisinformationFinding[]>(initialFindings)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(
    findingId: string,
    fn: () => Promise<MisinformationFinding>,
  ) {
    setBusyId(findingId)
    setError(null)
    try {
      const updated = await fn()
      setFindings((prev) => prev.map((f) => (f.id === findingId ? updated : f)))
    } catch {
      setError("That didn't go through. Reload the page and try again.")
    } finally {
      setBusyId(null)
    }
  }

  const needsReview = findings.filter((f) => f.status === "suggested").length

  return (
    <section className="space-y-4 rounded-lg border bg-card p-5">
      <div>
        <h2 className="font-display text-lg font-semibold tracking-tight">
          How AI represents this client
        </h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Statements flagged for your review — wrong facts, services they don&rsquo;t offer, or
          claims that create advertising risk. Every quote below is word-for-word from a stored AI
          answer. Nothing reaches the client&rsquo;s report until you confirm it. These are flags
          for review, not a compliance certification.
        </p>
        {needsReview > 0 && (
          <p className="mt-2 text-xs font-medium">
            {needsReview} awaiting your review
          </p>
        )}
      </div>

      {error && <p className="text-xs text-score-low">{error}</p>}

      {findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing flagged. The check runs automatically after each scan.
        </p>
      ) : (
        <ul className="space-y-3">
          {findings.map((f) => {
            const busy = busyId === f.id
            return (
              <li key={f.id} className="rounded-md border bg-background p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      SEVERITY_CHIP[f.severity],
                    )}
                  >
                    {f.severity === "high" ? "High" : f.severity === "medium" ? "Medium" : "Low"}
                  </span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      STATUS_CHIP[f.status],
                    )}
                  >
                    {STATUS_LABEL[f.status]}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {f.category_label} · {f.platform_label}
                  </span>
                </div>

                <blockquote className="mt-2 border-l-2 pl-3 text-sm leading-snug">
                  &ldquo;{f.quote}&rdquo;
                </blockquote>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {f.explanation}
                  {f.rule_text ? ` · Checklist: ${f.rule_text}` : ""}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Asked: &ldquo;{f.query_text}&rdquo;
                </p>
                {f.admin_note && (
                  <p className="mt-1 text-xs text-muted-foreground">Your note: {f.admin_note}</p>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {busy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                  {/* Dismissed findings keep a Confirm button: dismissing is a
                      judgement call the admin can reverse. Once a finding is in
                      the fix pipeline the backend refuses re-review (409). */}
                  {(f.status === "suggested" || f.status === "dismissed") && (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy}
                      aria-label={`Confirm finding: ${f.quote}`}
                      onClick={() =>
                        run(f.id, () => reviewMisinformationAction(clientId, f.id, "confirm"))
                      }
                    >
                      {f.status === "dismissed" ? "Confirm after all" : "Confirm"}
                    </Button>
                  )}
                  {f.status === "suggested" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      aria-label={`Dismiss finding: ${f.quote}`}
                      onClick={() =>
                        run(f.id, () => reviewMisinformationAction(clientId, f.id, "dismiss"))
                      }
                    >
                      Dismiss
                    </Button>
                  )}
                  {f.status === "confirmed" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      aria-label={`Mark fix submitted for: ${f.quote}`}
                      onClick={() =>
                        run(f.id, () => markMisinformationCorrectedAction(clientId, f.id))
                      }
                    >
                      Mark fix submitted
                    </Button>
                  )}
                  {f.status === "candidate_fixed" && (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy}
                      aria-label={`Confirm fixed: ${f.quote}`}
                      onClick={() => run(f.id, () => resolveMisinformationAction(clientId, f.id))}
                    >
                      Confirm fixed
                    </Button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
