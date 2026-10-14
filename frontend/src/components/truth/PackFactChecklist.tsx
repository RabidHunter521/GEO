import { CheckCircle2, Circle, Clock } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import type { PackFactChecklistItem } from "@/types"

const STATUS = {
  approved: { icon: CheckCircle2, label: "Approved", tone: "text-emerald-600 dark:text-emerald-400" },
  draft: { icon: Clock, label: "Draft awaiting approval", tone: "text-amber-600 dark:text-amber-400" },
  missing: { icon: Circle, label: "Not added", tone: "text-muted-foreground" },
} as const

/**
 * The pack facts to approve first. Scan questions are built from APPROVED
 * facts only, so a missing fact silently drops its questions from the scan;
 * this card is the only place that says so before a scan is run.
 */
export function PackFactChecklist({ items }: { items: PackFactChecklistItem[] }) {
  if (items.length === 0) return null
  const approved = items.filter((item) => item.status === "approved").length
  // Unfinished first, the ones that unlock the most questions on top.
  const ordered = [...items].sort((a, b) =>
    Number(a.status === "approved") - Number(b.status === "approved")
    || b.question_count - a.question_count
    || Number(b.required) - Number(a.required))

  return (
    <Card>
      <CardContent className="space-y-4 py-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-display text-lg font-semibold tracking-tight">Facts this pack needs</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Scan questions are built from approved facts only. Until a fact is approved, the
              questions it fills are left out of the scan. Drafts do not count.
            </p>
          </div>
          <Badge variant={approved === items.length ? "secondary" : "outline"}>
            {approved} of {items.length} approved
          </Badge>
        </div>
        <ul className="divide-y rounded-md border">
          {ordered.map((item) => {
            const status = STATUS[item.status]
            const Icon = status.icon
            return (
              <li key={`${item.fact_type}.${item.fact_key}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
                <Icon className={`h-4 w-4 shrink-0 ${status.tone}`} aria-hidden />
                <span className="min-w-0 flex-1 text-sm font-medium">{item.label}</span>
                <span className="flex flex-wrap items-center gap-1.5">
                  {item.question_count > 0 && (
                    <Badge variant="outline">
                      Fills {item.question_count} scan question{item.question_count === 1 ? "" : "s"}
                    </Badge>
                  )}
                  {item.required && <Badge variant="outline">Required</Badge>}
                  {item.risk_sensitive && (
                    <Badge variant="outline" className="border-amber-500/50 text-amber-600">
                      Checked against AI answers
                    </Badge>
                  )}
                  <span className={`text-xs ${status.tone}`}>{status.label}</span>
                </span>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
