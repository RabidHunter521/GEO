// frontend/src/components/clients/ClientCard.tsx
"use client"

import Link from "next/link"
import { Check } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { scoreDelta } from "@/lib/client-list-utils"
import { getScoreColor } from "@/lib/score-utils"
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

function initials(name: string | null | undefined) {
  return (name ?? "")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
}

// Gradient backgrounds for the avatar — cycles through a small palette by first letter
const AVATAR_GRADIENTS = [
  "from-violet-500 to-purple-700",
  "from-blue-500 to-indigo-700",
  "from-emerald-500 to-teal-700",
  "from-orange-500 to-rose-600",
  "from-pink-500 to-fuchsia-700",
  "from-sky-500 to-blue-700",
  "from-amber-500 to-orange-600",
]

function avatarGradient(name: string | null | undefined): string {
  const char = (name ?? "A")[0]?.toUpperCase() ?? "A"
  const idx = (char.charCodeAt(0) - 65) % AVATAR_GRADIENTS.length
  return AVATAR_GRADIENTS[Math.abs(idx)] ?? AVATAR_GRADIENTS[0]
}

// Score-color bottom accent bar
const SCORE_BAR: Record<string, string> = {
  green:  "bg-score-strong",
  yellow: "bg-score-watch",
  red:    "bg-score-low",
}

function DeltaIndicator({ client }: { client: ClientListItem }) {
  const delta = scoreDelta(client)
  if (delta === null || Math.round(delta) === 0) return null
  const rounded = Math.round(delta)
  return (
    <span
      className={cn(
        "text-xs font-semibold tabular-nums",
        rounded > 0 ? "text-score-strong" : "text-score-low",
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
  const nextScanDue = client.next_scan_due
    ? new Date(client.next_scan_due).toLocaleDateString("en-MY", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null

  const scoreColor =
    client.latest_overall_score !== null
      ? getScoreColor(client.latest_overall_score)
      : null

  const card = (
    <Card
      className={cn(
        "relative h-full overflow-hidden transition-all duration-200",
        !selectMode && "group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-brand",
        selectMode && selected && isDestructive && "border-destructive/50 ring-1 ring-destructive/30",
        selectMode && selected && !isDestructive && "border-primary/50 ring-1 ring-primary/30",
      )}
    >
      {/* Score-color bottom accent strip */}
      {scoreColor && (
        <span
          className={cn(
            "absolute bottom-0 left-0 right-0 h-[3px] rounded-b-[inherit] opacity-70",
            SCORE_BAR[scoreColor],
          )}
        />
      )}

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

      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3 pt-4">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-sm font-bold text-white shadow-sm",
              avatarGradient(client.name),
            )}
          >
            {initials(client.name)}
          </span>
          <div className="min-w-0">
            <p className="truncate font-semibold leading-tight">{client.name}</p>
            <p className="truncate text-xs text-muted-foreground/80">{host}</p>
          </div>
        </div>
        {!selectMode && (
          <span className="ml-2 flex shrink-0 items-center gap-1.5">
            <DeltaIndicator client={client} />
            <ScoreBadge score={client.latest_overall_score} />
          </span>
        )}
      </CardHeader>

      <CardContent className="flex items-center justify-between gap-2 pb-5">
        <p className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{client.industry}</p>
        <div className="shrink-0 flex flex-col items-end gap-1">
          {client.is_scan_overdue && !scanning && (
            <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 ring-1 ring-inset ring-amber-600/20">
              Scan due
            </span>
          )}
          <p className="text-xs text-muted-foreground/80">
            {scanning
              ? "Scanning…"
              : lastScan
              ? `Last scan ${lastScan}`
              : "No scans yet"}
          </p>
          {!scanning && !client.is_scan_overdue && nextScanDue && (
            <p className="text-[10px] text-muted-foreground/50">Next: {nextScanDue}</p>
          )}
        </div>
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
