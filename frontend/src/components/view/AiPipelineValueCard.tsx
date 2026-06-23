// frontend/src/components/view/AiPipelineValueCard.tsx
// The one money number: latest-month AI-referral visitors turned into an
// estimated pipeline in RM. RM figures only render when the SeenBy team has
// configured the client's deal value — otherwise we show the visitor count and
// an honest "tracking value" note rather than inventing revenue.
import { TrendingUp } from "lucide-react"
import type { ClientViewTrafficValue } from "@/types"

function rm(n: number): string {
  return `RM ${n.toLocaleString("en-MY")}`
}

export function AiPipelineValueCard({ value }: { value: ClientViewTrafficValue }) {
  const hasRevenue = value.est_pipeline_rm !== null

  return (
    <div className="relative overflow-hidden rounded-2xl border bg-card p-6 shadow-brand">
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-primary/[0.07] blur-3xl"
      />
      <div className="relative flex items-center gap-2">
        <span aria-hidden className="h-3.5 w-1 shrink-0 rounded-full bg-primary/70" />
        <TrendingUp className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          What AI Visibility Is Worth
        </h2>
      </div>

      {hasRevenue ? (
        <>
          <p className="mt-3 font-display text-3xl font-bold tabular-nums text-foreground">
            {rm(value.est_pipeline_rm as number)}{" "}
            <span className="ml-2 align-middle text-sm font-medium text-muted-foreground">
              estimated pipeline this month
            </span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            ≈ {value.ai_visitors.toLocaleString("en-MY")} visitors arrived from AI
            search → about {(value.est_leads as number).toLocaleString("en-MY")} leads →{" "}
            <span className="font-semibold text-foreground">
              {rm(value.est_won_rm as number)}
            </span>{" "}
            in estimated won business.
          </p>
        </>
      ) : (
        <>
          <p className="mt-3 font-display text-3xl font-bold tabular-nums text-foreground">
            {value.ai_visitors.toLocaleString("en-MY")}{" "}
            <span className="ml-2 align-middle text-sm font-medium text-muted-foreground">
              visitors from AI search this month
            </span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            People are finding you through ChatGPT, Perplexity, Gemini and Claude.
            We&apos;ll translate this into pipeline value with your team shortly.
          </p>
        </>
      )}
    </div>
  )
}
