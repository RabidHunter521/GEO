"use client"

import { useState, useTransition } from "react"
import {
  Loader2, Copy, ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight,
  CheckCircle, AlertTriangle, XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/utils"
import { getScoreColor } from "@/lib/score-utils"
import { runPageAuditAction, getPageAuditDetailAction } from "./actions"
import type { PageAudit, PageAuditListItem } from "@/types"

const SCORE_CLASSES: Record<string, string> = {
  green: "border-score-strong/30 bg-score-strong-bg text-score-strong",
  yellow: "border-score-watch/30 bg-score-watch-bg text-score-watch",
  red: "border-destructive/30 bg-destructive/10 text-destructive",
}

function ScoreChip({ score }: { score: number }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-sm font-semibold tabular-nums ${
        SCORE_CLASSES[getScoreColor(score)]
      }`}
    >
      {score}
    </span>
  )
}

function StatusIcon({ status }: { status: "pass" | "warn" | "fail" }) {
  if (status === "pass") return <CheckCircle className="h-3.5 w-3.5 text-score-strong shrink-0" />
  if (status === "warn") return <AlertTriangle className="h-3.5 w-3.5 text-score-watch shrink-0" />
  return <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
}

export function PageAuditsSection({
  clientId,
  initialAudits,
}: {
  clientId: string
  initialAudits: PageAuditListItem[]
}) {
  const [audits, setAudits] = useState<PageAuditListItem[]>(initialAudits)
  const [url, setUrl] = useState("")
  const [runError, setRunError] = useState<string | null>(null)
  const [running, startRun] = useTransition()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PageAudit | null>(null)
  const [loadingDetail, startDetail] = useTransition()

  function handleRun() {
    if (!url.trim()) return
    setRunError(null)
    startRun(async () => {
      try {
        const audit = await runPageAuditAction(clientId, url.trim())
        setAudits((prev) => {
          const rest = prev.filter((a) => a.url !== audit.url)
          const previous = prev.find((a) => a.url === audit.url)
          return [
            {
              id: audit.id, url: audit.url, score: audit.score,
              previous_score: previous ? previous.score : null,
              created_at: audit.created_at,
            },
            ...rest,
          ]
        })
        setDetail(audit)
        setExpandedId(audit.id)
        setUrl("")
      } catch (e) {
        setRunError(
          e instanceof Error && e.message.includes("422")
            ? "That page isn't on this client's website."
            : "Couldn't audit that page — check the address and try again.",
        )
      }
    })
  }

  function handleExpand(item: PageAuditListItem) {
    if (expandedId === item.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(item.id)
    setDetail(null)
    startDetail(async () => {
      try {
        setDetail(await getPageAuditDetailAction(clientId, item.id))
      } catch {
        setDetail(null)
      }
    })
  }

  async function handleCopy(text: string) {
    const ok = await copyToClipboard(text)
    toast[ok ? "success" : "error"](ok ? "Copied to clipboard" : "Couldn't copy.")
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <h3 className="font-display text-lg font-semibold">Page Audits</h3>
      <p className="text-sm text-muted-foreground mt-1">
        Score any page on the client&apos;s site for how easily AI assistants can read
        and quote it. Informational only — not part of the GEO score.
      </p>

      <div className="mt-4 flex gap-2">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleRun()}
          placeholder="https://clientdomain.com/services"
          className="max-w-xl"
        />
        <Button onClick={handleRun} disabled={running || !url.trim()}>
          {running && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {running ? "Auditing…" : "Run audit"}
        </Button>
      </div>
      {runError && <p className="mt-2 text-sm text-destructive">{runError}</p>}

      {audits.length === 0 && !running && (
        <p className="mt-4 text-sm text-muted-foreground">
          No pages audited yet — paste a page address above to start.
        </p>
      )}

      {audits.length > 0 && (
        <div className="mt-4 divide-y rounded-md border">
          {audits.map((item) => (
            <div key={item.id}>
              <button
                onClick={() => handleExpand(item)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/30"
              >
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{item.url}</span>
                <span className="flex shrink-0 items-center gap-3">
                  {item.previous_score !== null && item.previous_score !== item.score && (
                    <span
                      className={`flex items-center gap-0.5 text-xs tabular-nums ${
                        item.score > item.previous_score ? "text-score-strong" : "text-destructive"
                      }`}
                    >
                      {item.score > item.previous_score ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      was {item.previous_score}
                    </span>
                  )}
                  <ScoreChip score={item.score} />
                  <span className="text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleDateString("en-MY", {
                      day: "numeric", month: "short",
                    })}
                  </span>
                  {expandedId === item.id ? (
                    <ChevronUp className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  )}
                </span>
              </button>

              {expandedId === item.id && (
                <div className="border-t bg-muted/10 px-4 py-4">
                  {loadingDetail && !detail && (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                  {detail && detail.id === item.id && (
                    <div className="space-y-4">
                      <div className="divide-y rounded-md border bg-card">
                        {detail.checks.map((check) => (
                          <div key={check.id} className="flex items-start gap-2.5 px-3 py-2">
                            <StatusIcon status={check.status} />
                            <div className="min-w-0">
                              <p className="text-sm font-medium">
                                {check.label}{" "}
                                <span className="text-xs font-normal text-muted-foreground tabular-nums">
                                  {check.points} pts
                                </span>
                              </p>
                              <p className="text-xs text-muted-foreground">{check.detail}</p>
                            </div>
                          </div>
                        ))}
                      </div>

                      {detail.suggestions.length > 0 && (
                        <div>
                          <p className="mb-2 text-sm font-semibold">Suggested rewrites</p>
                          <div className="space-y-2">
                            {detail.suggestions.map((s, i) => (
                              <div key={i} className="rounded-md border bg-card px-3 py-2.5">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="min-w-0">
                                    <p className="text-sm font-medium">{s.section}</p>
                                    <p className="text-xs text-muted-foreground">{s.issue}</p>
                                  </div>
                                  <Button
                                    size="sm" variant="outline" className="h-7 shrink-0 text-xs"
                                    onClick={() => handleCopy(s.rewrite)}
                                  >
                                    <Copy className="h-3 w-3 mr-1" /> Copy
                                  </Button>
                                </div>
                                <p className="mt-2 whitespace-pre-wrap rounded bg-muted/30 px-2.5 py-2 text-sm">
                                  {s.rewrite}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {detail.suggestions_failed && (
                        <p className="text-sm text-muted-foreground">
                          Rewrite suggestions didn&apos;t generate this time —{" "}
                          <button
                            className="underline underline-offset-4"
                            onClick={() => {
                              setUrl(detail.url)
                              handleRun()
                            }}
                          >
                            retry the audit
                          </button>
                          .
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
