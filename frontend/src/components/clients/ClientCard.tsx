// frontend/src/components/clients/ClientCard.tsx
"use client"

import Link from "next/link"
import { Check } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { scoreDelta } from "@/lib/client-list-utils"
import { cn } from "@/lib/utils"
import type { ClientListItem } from "@/types"

interface Props {
  client: ClientListItem
  selectMode?: boolean
  selected?: boolean
  onToggle?: () => void
  // Tints the selection checkbox/ring: destructive for remove, primary for scan
  selectionVariant?: "destructive" | "primary"
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
}

function DeltaIndicator({ client }: { client: ClientListItem }) {
  const delta = scoreDelta(client)
  if (delta === null || Math.round(delta) === 0) return null
  const rounded = Math.round(delta)
  return (
    <span
      className={cn(
        "text-xs font-medium tabular-nums",
        rounded > 0 ? "text-emerald-600" : "text-red-600",
      )}
    >
      {rounded > 0 ? `+${rounded}` : `${rounded}`}
    </span>
  )
}

export function ClientCard({
  client,
  selectMode = false,
  selected = false,
  onToggle,
  selectionVariant = "destructive",
}: Props) {
  const host = client.website?.replace(/^https?:\/\//, "").replace(/\/$/, "")
  const lastScan = client.last_scan_at
    ? new Date(client.last_scan_at).toLocaleDateString("en-MY", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null
  const isDestructive = selectionVariant === "destructive"
  const scanning =
    client.latest_scan_status === "pending" || client.latest_scan_status === "running"

  const card = (
    <Card
      className={cn(
        "relative h-full transition-all duration-200",
        !selectMode && "group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-brand",
        selectMode && selected && isDestructive && "border-destructive/50 ring-1 ring-destructive/30",
        selectMode && selected && !isDestructive && "border-primary/50 ring-1 ring-primary/30",
      )}
    >
      {selectMode && (
        <span
          className={cn(
            "absolute right-3 top-3 z-10 flex h-5 w-5 items-center justify-center rounded-full border",
            selected
              ? isDestructive
                ? "border-destructive bg-destructive text-destructive-foreground"
                : "border-primary bg-primary text-primary-foreground"
              : "border-muted-foreground/30 bg-card",
          )}
        >
          {selected && <Check className="h-3.5 w-3.5" />}
        </span>
      )}
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
        {!selectMode && (
          <span className="ml-2 flex shrink-0 items-center gap-1.5">
            <DeltaIndicator client={client} />
            <ScoreBadge score={client.latest_overall_score} />
          </span>
        )}
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-2">
        <p className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{client.industry}</p>
        <p className="shrink-0 text-xs text-muted-foreground">
          {scanning ? "Scanning…" : lastScan ? `Last scan ${lastScan}` : "No scans yet"}
        </p>
      </CardContent>
    </Card>
  )

  if (selectMode) {
    return (
      <button type="button" onClick={onToggle} className="block w-full text-left">
        {card}
      </button>
    )
  }

  return (
    <Link href={`/clients/${client.id}`} className="group block">
      {card}
    </Link>
  )
}
