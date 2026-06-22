// frontend/src/components/clients/PortfolioSummary.tsx
// Portfolio-level stat row at the top of /clients. Always computed from the
// full (unfiltered) client list so it stays a truthful portfolio view.
"use client"

import { TrendingDown, TrendingUp, Users, AlertTriangle } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { attentionReasons, scoreDelta } from "@/lib/client-list-utils"
import { cn } from "@/lib/utils"
import type { ClientListItem } from "@/types"

interface Props {
  clients: ClientListItem[]
  now: Date
}

export function PortfolioSummary({ clients, now }: Props) {
  const scored = clients.filter((c) => c.latest_overall_score !== null)
  const average =
    scored.length > 0
      ? scored.reduce((sum, c) => sum + (c.latest_overall_score ?? 0), 0) / scored.length
      : null

  const deltas = clients.map(scoreDelta).filter((d): d is number => d !== null)
  const improved = deltas.filter((d) => d > 0).length
  const declined = deltas.filter((d) => d < 0).length
  const needsAttention = clients.filter((c) => attentionReasons(c, now).length > 0).length

  const stats = [
    {
      label: "Clients",
      icon: Users,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
      value: <span className="font-display text-2xl font-bold">{clients.length}</span>,
    },
    {
      label: "Average score",
      icon: null,
      iconBg: null,
      iconColor: null,
      value:
        average !== null ? (
          <span className="font-display text-2xl font-bold tabular-nums">
            {average.toFixed(0)}
          </span>
        ) : (
          <span className="font-display text-2xl font-bold text-muted-foreground">—</span>
        ),
    },
    {
      label: "Improved",
      icon: TrendingUp,
      iconBg: "bg-score-strong-bg",
      iconColor: "text-score-strong",
      value: (
        <span className="font-display text-2xl font-bold text-score-strong">{improved}</span>
      ),
    },
    {
      label: "Declined",
      icon: TrendingDown,
      iconBg: "bg-score-low-bg",
      iconColor: "text-score-low",
      value: <span className="font-display text-2xl font-bold text-score-low">{declined}</span>,
    },
    {
      label: "Needs attention",
      icon: AlertTriangle,
      iconBg: needsAttention > 0 ? "bg-score-watch-bg" : "bg-muted",
      iconColor: needsAttention > 0 ? "text-score-watch" : "text-muted-foreground",
      value: (
        <span
          className={cn(
            "font-display text-2xl font-bold",
            needsAttention > 0 ? "text-score-watch" : "",
          )}
        >
          {needsAttention}
        </span>
      ),
    },
  ]

  return (
    <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
      {stats.map((stat) => (
        <Card key={stat.label} className="transition-shadow hover:shadow-brand">
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              {stat.icon && stat.iconBg && stat.iconColor && (
                <span className={cn("flex h-7 w-7 items-center justify-center rounded-lg", stat.iconBg)}>
                  <stat.icon className={cn("h-3.5 w-3.5", stat.iconColor)} />
                </span>
              )}
              <p className="text-xs font-medium text-muted-foreground">{stat.label}</p>
            </div>
            <div className="mt-2">{stat.value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
