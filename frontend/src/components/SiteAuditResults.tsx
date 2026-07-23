// Shared grouped-results view for the site AI-readiness audit.
// Used by the toolkit page card and the competitors page inline audit.
import { CheckCircle, XCircle, AlertTriangle, HelpCircle } from "lucide-react"
import type { SiteAuditCheck, SiteAuditStatus } from "@/types"

const GROUPS: { title: string; ids: string[] }[] = [
  {
    title: "AI crawl access",
    ids: ["robots_exists", "robots_ai_bots", "llms_txt", "llms_full_txt", "https"],
  },
  { title: "Sitemap", ids: ["sitemap_exists", "sitemap_urls", "sitemap_fresh"] },
  {
    title: "Homepage signals",
    ids: [
      "title", "meta_description", "canonical", "open_graph", "h1",
      "heading_order", "viewport", "internal_links", "response_time",
    ],
  },
  { title: "Structured data", ids: ["jsonld_present", "jsonld_types"] },
]

function StatusChip({ status }: { status: SiteAuditStatus }) {
  if (status === "pass")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-score-strong">
        <CheckCircle className="h-3.5 w-3.5" /> Pass
      </span>
    )
  if (status === "warn")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-score-watch">
        <AlertTriangle className="h-3.5 w-3.5" /> Improve
      </span>
    )
  if (status === "fail")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-destructive">
        <XCircle className="h-3.5 w-3.5" /> Fix
      </span>
    )
  return (
    <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
      <HelpCircle className="h-3.5 w-3.5" /> Couldn&apos;t check
    </span>
  )
}

export function SiteAuditResults({ checks }: { checks: SiteAuditCheck[] }) {
  const byId = new Map(checks.map((c) => [c.id, c]))
  return (
    <div className="space-y-5">
      {GROUPS.map((group) => {
        const groupChecks = group.ids
          .map((id) => byId.get(id))
          .filter((c): c is SiteAuditCheck => c !== undefined)
        if (groupChecks.length === 0) return null
        return (
          <div key={group.title}>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              {group.title}
            </p>
            <div className="divide-y rounded-md border">
              {groupChecks.map((check) => (
                <div key={check.id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium">{check.label}</span>
                    <StatusChip status={check.status} />
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{check.detail}</p>
                  {check.fix && (
                    <p className="mt-1 text-xs text-foreground/80">
                      <span className="font-medium">How to fix:</span> {check.fix}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
