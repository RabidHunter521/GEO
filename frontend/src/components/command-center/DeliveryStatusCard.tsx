// frontend/src/components/command-center/DeliveryStatusCard.tsx
// Work pipeline counts, read straight off stored statuses. Deliberately three
// rows only — DeliverySummary has no "waiting for client" state (see
// backend/app/schemas/command_center.py). Never fabricate a fourth row.
import Link from "next/link"

import type { DeliverySummary } from "@/types"

interface Props {
  summary: DeliverySummary
  clientId: string
}

export function DeliveryStatusCard({ summary, clientId }: Props) {
  const rows: { label: string; count: number; href: string }[] = [
    { label: "In progress", count: summary.in_progress, href: `/clients/${clientId}/scan` },
    { label: "Ready to publish", count: summary.ready_to_publish, href: `/clients/${clientId}/activity` },
    { label: "Completed (last 30 days)", count: summary.completed_last_30d, href: `/clients/${clientId}/activity` },
  ]

  return (
    <div className="rounded-lg border bg-card p-5">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
        Delivery Status
      </h2>
      <div className="space-y-1">
        {rows.map((row) => (
          <Link
            key={row.label}
            href={row.href}
            className="-mx-2 flex items-center justify-between rounded-md px-2 py-2 transition-colors hover:bg-muted/50"
          >
            <span className="text-sm text-foreground">{row.label}</span>
            <span className="font-display text-lg font-bold tabular-nums text-foreground">
              {row.count}
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
