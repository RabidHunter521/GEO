// frontend/src/components/competitors/WinLossSection.tsx
"use client"

import { useState, useTransition } from "react"
import { CheckCircle, XCircle, Loader2, Sparkles, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { ContentBrief, WinLossEntry, WinLossResponse } from "@/types"
import { PLATFORM_LABELS } from "@/types"
import { generateBriefAction } from "@/app/clients/[id]/competitors/actions"

const CATEGORY_LABELS: Record<string, string> = {
  recommendation: "Recommendation",
  local: "Local",
}

const OUTCOME_ORDER = ["lost", "open", "shared", "won"] as const

const OUTCOME_LABELS: Record<string, string> = {
  lost: "Your competitors are winning here",
  open: "Open — nobody seen yet",
  shared: "Shared with competitors",
  won: "Won",
}

interface Props {
  clientId: string
  data: WinLossResponse
}

export function WinLossSection({ clientId, data }: Props) {
  const [briefs, setBriefs] = useState<Record<string, ContentBrief>>(() => {
    const initial: Record<string, ContentBrief> = {}
    for (const e of data.entries) {
      if (e.brief) initial[e.result_id] = e.brief
    }
    return initial
  })
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [errorId, setErrorId] = useState<string | null>(null)
  const [, startTransition] = useTransition()

  if (data.entries.length === 0) return null

  function handleGenerate(resultId: string) {
    setPendingId(resultId)
    setErrorId(null)
    startTransition(async () => {
      try {
        const brief = await generateBriefAction(clientId, resultId)
        setBriefs((prev) => ({ ...prev, [resultId]: brief }))
      } catch {
        setErrorId(resultId)
      } finally {
        setPendingId(null)
      }
    })
  }

  const summary = data.summary

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Win / Loss by Query</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Head-to-head on neutral questions (recommendation + local) from the latest scan.
        </p>
      </div>

      {/* Summary chips */}
      <div className="flex flex-wrap gap-2">
        <span className="rounded-full bg-score-strong-bg px-3 py-1 text-xs font-medium text-score-strong">
          Won {summary.won ?? 0}
        </span>
        <span className="rounded-full bg-score-watch-bg px-3 py-1 text-xs font-medium text-score-watch">
          Your competitors are winning here ({summary.lost ?? 0})
        </span>
        <span className="rounded-full border bg-muted/30 px-3 py-1 text-xs text-muted-foreground">
          Shared {summary.shared ?? 0}
        </span>
        <span className="rounded-full border bg-muted/30 px-3 py-1 text-xs text-muted-foreground">
          Open {summary.open ?? 0}
        </span>
      </div>

      {OUTCOME_ORDER.map((outcome) => {
        const entries = data.entries.filter((e) => e.outcome === outcome)
        if (entries.length === 0) return null
        return (
          <div key={outcome}>
            <h4
              className={`mb-2 text-xs font-semibold uppercase tracking-wide ${
                outcome === "lost"
                  ? "text-score-watch"
                  : outcome === "won"
                    ? "text-score-strong"
                    : "text-muted-foreground"
              }`}
            >
              {OUTCOME_LABELS[outcome]} — {entries.length}
            </h4>
            <div className="space-y-2">
              {entries.map((entry) => (
                <WinLossRow
                  key={entry.result_id}
                  entry={entry}
                  brief={briefs[entry.result_id] ?? null}
                  pending={pendingId === entry.result_id}
                  failed={errorId === entry.result_id}
                  onGenerate={() => handleGenerate(entry.result_id)}
                />
              ))}
            </div>
          </div>
        )
      })}
    </section>
  )
}

function WinLossRow({
  entry,
  brief,
  pending,
  failed,
  onGenerate,
}: {
  entry: WinLossEntry
  brief: ContentBrief | null
  pending: boolean
  failed: boolean
  onGenerate: () => void
}) {
  const canGenerate = !entry.client_seen // lost + open queries only

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="shrink-0 text-xs font-medium w-20">
            {PLATFORM_LABELS[entry.platform] ?? entry.platform}
          </span>
          <Badge variant="outline" className="shrink-0 text-xs font-normal">
            {CATEGORY_LABELS[entry.category] ?? entry.category}
          </Badge>
          <span className="truncate text-sm text-muted-foreground">
            &ldquo;{entry.query_text}&rdquo;
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {entry.client_seen ? (
            <span className="flex items-center gap-1.5 text-xs font-medium text-score-strong">
              <CheckCircle className="h-3.5 w-3.5" />
              Seen by AI
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <XCircle className="h-3.5 w-3.5" />
              Not seen by AI
            </span>
          )}
          {canGenerate && !brief && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={onGenerate}
              disabled={pending}
            >
              {pending ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-3 w-3" />
              )}
              {pending ? "Generating…" : "Generate content brief"}
            </Button>
          )}
        </div>
      </div>

      {entry.competitors_seen.length > 0 && (
        <p className="mt-2 text-xs text-score-watch">
          Seen by AI instead: {entry.competitors_seen.join(", ")}
        </p>
      )}

      {failed && (
        <p className="mt-2 text-xs text-destructive">
          Brief generation failed — try again.
        </p>
      )}

      {brief && (
        <div className="mt-3 rounded-md border bg-muted/20 p-4">
          <div className="flex items-start justify-between gap-3">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <FileText className="h-4 w-4 shrink-0 text-primary" />
              {brief.title}
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 shrink-0 px-2 text-xs text-muted-foreground"
              onClick={onGenerate}
              disabled={pending}
            >
              {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Regenerate"}
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{brief.angle}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {brief.outline.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground/70">
            Generated{" "}
            {new Date(brief.generated_at).toLocaleDateString("en-MY", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </p>
        </div>
      )}
    </div>
  )
}
