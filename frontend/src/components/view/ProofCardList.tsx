// frontend/src/components/view/ProofCardList.tsx
// Verbatim, client-safe AI answer cards. Wins are flattering proof ("here's
// what ChatGPT said about you"); losses are honest opportunity ("a competitor
// was recommended, not you"). Excerpts are competitor-redacted server-side;
// raw responses never reach this surface.
import { Quote } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ClientViewProofCard } from "@/types"

function cardHeader(card: ClientViewProofCard): string {
  return card.kind === "win"
    ? `What ${card.platform_label} said about you`
    : `${card.platform_label} recommended a competitor — they're winning this question`
}

export function ProofCardList({ cards }: { cards: ClientViewProofCard[] }) {
  if (!cards || cards.length === 0) return null
  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Straight From AI Search
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {cards.map((card, i) => {
          const isWin = card.kind === "win"
          return (
            <div
              key={`${card.platform_label}-${card.category}-${i}`}
              className={cn(
                "rounded-lg border bg-card p-4",
                isWin ? "border-score-strong/30" : "border-score-watch/30",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="rounded-full border bg-muted/30 px-2.5 py-0.5 text-xs font-medium">
                  {card.platform_label}
                </span>
                <span
                  className={cn(
                    "text-xs font-semibold",
                    isWin ? "text-score-strong" : "text-score-watch",
                  )}
                >
                  {isWin ? "Seen by AI" : "Opportunity"}
                </span>
              </div>
              <p className="mt-2 text-sm font-medium text-foreground">{cardHeader(card)}</p>
              <blockquote className="mt-2 flex gap-2">
                <Quote className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <p className="text-sm italic leading-relaxed text-muted-foreground">
                  &ldquo;{card.excerpt}&rdquo;
                </p>
              </blockquote>
            </div>
          )
        })}
      </div>
    </div>
  )
}
