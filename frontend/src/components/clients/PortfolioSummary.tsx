// frontend/src/components/clients/PortfolioSummary.tsx
// Portfolio-level stat row at the top of /clients. Always computed from the
// full (unfiltered) client list so it stays a truthful portfolio view.
"use client"

import { TrendingDown, TrendingUp, Users, AlertTriangle } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { attentionReasons, scoreDelta } from "@/lib/client-list-utils"
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
      value: <span className="font-display text-2xl font-bold">{clients.length}</span>,
    },
    {
      label: "Average score",
      icon: null,
      value:
        average !== null ? (
          <span className="flex items-center gap-2">
            <span className="font-display text-2xl font-bold tabular-nums">
              {average.toFixed(0)}
            </span>
            <ScoreBadge score={average} />
          </span>
        ) : (
          <span className="font-display text-2xl font-bold text-muted-foreground">—</span>
        ),
    },
    {
      label: "Improved",
      icon: TrendingUp,
      value: (
        <span className="font-display text-2xl font-bold text-emerald-600">{improved}</span>
      ),
    },
    {
      label: "Declined",
      icon: TrendingDown,
      value: <span className="font-display text-2xl font-bold text-red-600">{declined}</span>,
    },
    {
      label: "Needs attention",
      icon: AlertTriangle,
      value: (
        <span
          className={
            needsAttention > 0
              ? "font-display text-2xl font-bold text-amber-600"
              : "font-display text-2xl font-bold"
          }
        >
          {needsAttention}
        </span>
      ),
    },
  ]

  return (
    <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="p-4">
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {stat.icon && <stat.icon className="h-3.5 w-3.5" />}
              {stat.label}
            </p>
            <div className="mt-1">{stat.value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
