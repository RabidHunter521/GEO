"use client"

import { useState, useTransition } from "react"
import { Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SiteAuditResults } from "@/components/SiteAuditResults"
import { runSiteAuditAction } from "@/app/clients/[id]/toolkit/actions"
import type { SiteAuditLatest } from "@/types"

export function SiteAuditCard({
  clientId,
  initialLatest,
}: {
  clientId: string
  initialLatest: SiteAuditLatest | null
}) {
  const [latest, setLatest] = useState<SiteAuditLatest | null>(initialLatest)
  const [failed, setFailed] = useState(false)
  const [pending, startTransition] = useTransition()

  function handleRun() {
    setFailed(false)
    startTransition(async () => {
      try {
        setLatest(await runSiteAuditAction(clientId))
      } catch {
        setFailed(true)
      }
    })
  }

  const audit = latest?.audit ?? null

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-lg font-semibold">Site AI-Readiness Audit</h3>
          <p className="text-sm text-muted-foreground mt-1">
            19 checks across AI crawl access, sitemap, homepage signals and structured
            data — each with a plain-English fix. Informational only, not part of the score.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRun} disabled={pending} className="shrink-0">
          {pending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          )}
          {pending ? "Auditing…" : audit ? "Run again" : "Run audit"}
        </Button>
      </div>

      {failed && (
        <p className="mt-3 text-sm text-destructive">Couldn&apos;t complete the audit — try again.</p>
      )}

      {audit && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>
              <span className="font-semibold text-score-strong">{audit.passed}</span> passed
              {" · "}
              <span className="font-semibold text-score-watch">{audit.warned}</span> to improve
              {" · "}
              <span className="font-semibold text-destructive">{audit.failed}</span> to fix
              {audit.unknown > 0 && (
                <>
                  {" · "}
                  {audit.unknown} couldn&apos;t check
                </>
              )}
            </span>
            <span>
              Last run{" "}
              {new Date(audit.created_at).toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
            {latest?.has_previous && (
              <span>
                Since last audit: {latest.fixed.length} fixed
                {latest.regressed.length > 0 && ` · ${latest.regressed.length} got worse`}
              </span>
            )}
          </div>
          <div className="mt-4">
            <SiteAuditResults checks={audit.checks} />
          </div>
        </>
      )}

      {!audit && !pending && (
        <p className="mt-4 text-sm text-muted-foreground">
          No audit yet — run one to see how ready this site is for AI search.
        </p>
      )}
    </div>
  )
}
