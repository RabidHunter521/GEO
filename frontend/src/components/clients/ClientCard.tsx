// frontend/src/components/clients/ClientCard.tsx
import Link from "next/link"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import type { ClientListItem } from "@/types"

interface Props {
  client: ClientListItem
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
}

export function ClientCard({ client }: Props) {
  const host = client.website?.replace(/^https?:\/\//, "").replace(/\/$/, "")
  const lastScan = client.last_scan_at
    ? new Date(client.last_scan_at).toLocaleDateString("en-MY", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null

  return (
    <Link href={`/clients/${client.id}`} className="group block">
      <Card className="h-full transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-brand">
        <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 font-display text-sm font-semibold text-primary">
              {initials(client.name)}
            </span>
            <div className="min-w-0">
              <p className="truncate font-semibold">{client.name}</p>
              <p className="truncate text-xs text-muted-foreground">{host}</p>
            </div>
          </div>
          <ScoreBadge score={client.latest_overall_score} className="ml-2 shrink-0" />
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">{client.industry}</p>
          <p className="text-xs text-muted-foreground">
            {lastScan ? `Last scan ${lastScan}` : "No scans yet"}
          </p>
        </CardContent>
      </Card>
    </Link>
  )
}
