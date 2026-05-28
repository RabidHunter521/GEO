// frontend/src/components/clients/ClientCard.tsx
import Link from "next/link"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import type { ClientListItem } from "@/types"

interface Props {
  client: ClientListItem
}

export function ClientCard({ client }: Props) {
  const lastScan = client.last_scan_at
    ? new Date(client.last_scan_at).toLocaleDateString("en-MY", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null

  return (
    <Link href={`/clients/${client.id}`} className="block group">
      <Card className="h-full transition-shadow group-hover:shadow-md">
        <CardHeader className="pb-2 flex flex-row items-start justify-between space-y-0">
          <div className="min-w-0">
            <p className="font-semibold truncate">{client.name}</p>
            <p className="text-xs text-muted-foreground truncate">{client.website}</p>
          </div>
          <ScoreBadge score={client.latest_overall_score} className="ml-2 shrink-0" />
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">{client.industry}</p>
          <p className="text-xs text-muted-foreground mt-1">
            {lastScan ? `Last scan ${lastScan}` : "No scans yet"}
          </p>
        </CardContent>
      </Card>
    </Link>
  )
}
