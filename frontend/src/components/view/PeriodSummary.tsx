// frontend/src/components/view/PeriodSummary.tsx
// Deterministic, plain-English period summary — rendered immediately after
// the public overview hero, above the detailed evidence sections (proof
// cards, score breakdown, remediation loop). Every sentence here is built
// server-side from stored values (client_period_summary_service); this
// component only renders the strings it's given — no client-side
// computation, no LLM output, nothing beyond what the API already sent.
import type { ComponentType } from "react"
import { ArrowRight, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react"
import { SectionHeading } from "@/components/view/SectionHeading"
import { cn } from "@/lib/utils"
import type { ClientViewPeriodSummary } from "@/types"

interface EvidenceLink {
  href: string
  label: string
}

interface ListBlockProps {
  title: string
  items: string[]
  icon: ComponentType<{ className?: string }>
  iconClass: string
  evidence?: EvidenceLink
}

function ListBlock({ title, items, icon: Icon, iconClass, evidence }: ListBlockProps) {
  if (items.length === 0) return null
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h3>
        {evidence && (
          <a
            href={evidence.href}
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            {evidence.label}
            <ArrowRight className="h-3 w-3" />
          </a>
        )}
      </div>
      <ul className="mt-3 space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm leading-relaxed text-foreground">
            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

interface Props {
  summary: ClientViewPeriodSummary
  /** Whether the "Straight From AI Search" proof-card section renders below. */
  hasEvidence: boolean
  /** Whether the "What We're Fixing" remediation loop renders below. */
  hasProgress: boolean
  /** Whether the "What We're Working On" actions section renders below. */
  hasActions: boolean
}

export function PeriodSummary({ summary, hasEvidence, hasProgress, hasActions }: Props) {
  const hasAnyList =
    summary.wins.length > 0 ||
    summary.risks.length > 0 ||
    summary.work_underway.length > 0 ||
    summary.next_actions.length > 0

  return (
    <section className="reveal" style={{ animationDelay: "30ms" }} aria-label="Period summary">
      <SectionHeading>This Period, In Plain English</SectionHeading>
      <div className="rounded-xl border bg-card p-5">
        <p className="text-sm font-medium leading-relaxed text-foreground">{summary.headline}</p>
        {hasAnyList && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <ListBlock
              title="Wins"
              items={summary.wins}
              icon={CheckCircle2}
              iconClass="text-score-strong"
              evidence={hasEvidence ? { href: "#proof-cards", label: "View evidence" } : undefined}
            />
            <ListBlock
              title="Risks"
              items={summary.risks}
              icon={AlertTriangle}
              iconClass="text-score-low"
              evidence={hasProgress ? { href: "#progress", label: "View evidence" } : undefined}
            />
            <ListBlock
              title="Work Underway"
              items={summary.work_underway}
              icon={Loader2}
              iconClass="text-score-watch"
              evidence={hasProgress ? { href: "#progress", label: "View evidence" } : undefined}
            />
            <ListBlock
              title="Next Actions"
              items={summary.next_actions}
              icon={ArrowRight}
              iconClass="text-primary"
              evidence={hasActions ? { href: "#working-on", label: "View evidence" } : undefined}
            />
          </div>
        )}
      </div>
    </section>
  )
}
