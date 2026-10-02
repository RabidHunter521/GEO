"use client"

import { useMemo, useState } from "react"
import { ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DEFAULT_FILTERS, PLACEMENT_CATEGORY_LABEL, PLACEMENT_STATUS_LABEL, filterPlacements, scoreTone,
  type PlacementFilters, type StatusFilter,
} from "@/lib/placements"
import { PLATFORM_LABELS, SCAN_PLATFORMS } from "@/types"
import type { PlacementCategory, PlacementTarget, Platform } from "@/types"
import { PlacementDetailDialog } from "./PlacementDetailDialog"

// Defined score tokens (tailwind.config.ts); -bg/-fg pairs clear WCAG AA.
const TONE_CLASS = {
  high: "bg-score-strong-bg text-score-strong",
  medium: "bg-score-watch-bg text-score-watch-fg",
  low: "bg-muted text-muted-foreground",
} as const

export function PlacementSection({
  clientId, initialTargets,
}: {
  clientId: string
  initialTargets: PlacementTarget[]
}) {
  const [targets, setTargets] = useState(initialTargets)
  const [filters, setFilters] = useState<PlacementFilters>(DEFAULT_FILTERS)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const rows = useMemo(() => filterPlacements(targets, filters), [targets, filters])

  function replace(updated: PlacementTarget) {
    setTargets((ts) => ts.map((t) => (t.id === updated.id ? { ...t, ...updated } : t)))
  }

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="font-display text-lg">Placement opportunities</CardTitle>
        <p className="text-sm text-muted-foreground">
          Third-party pages AI answers drew on for this client&apos;s buyer questions that don&apos;t
          name them yet, ranked by how much winning each one is worth. Refreshed after every scan.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Select value={filters.status} onValueChange={(v) => setFilters({ ...filters, status: v as StatusFilter })}>
            <SelectTrigger className="w-40" aria-label="Status"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="active">Active</SelectItem>
              {Object.entries(PLACEMENT_STATUS_LABEL).map(([value, label]) => (
                <SelectItem key={value} value={value}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filters.category}
            onValueChange={(v) => setFilters({ ...filters, category: v as PlacementCategory | "all" })}>
            <SelectTrigger className="w-40" aria-label="Category"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {Object.entries(PLACEMENT_CATEGORY_LABEL).map(([value, label]) => (
                <SelectItem key={value} value={value}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filters.platform}
            onValueChange={(v) => setFilters({ ...filters, platform: v as Platform | "all" })}>
            <SelectTrigger className="w-40" aria-label="AI platform"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All platforms</SelectItem>
              {SCAN_PLATFORMS.map((p) => <SelectItem key={p} value={p}>{PLATFORM_LABELS[p]}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {targets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No placement opportunities yet. They appear after a scan once SeenBy has checked the pages
            AI answers drew on.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing matches these filters.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">Score</TableHead>
                <TableHead>Page</TableHead>
                <TableHead>Why it matters</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow key={t.id} className="cursor-pointer" onClick={() => setSelectedId(t.id)}>
                  <TableCell>
                    <span className={`rounded px-2 py-0.5 text-sm font-semibold tabular-nums ${TONE_CLASS[scoreTone(t.priority_score)]}`}>
                      {t.priority_score}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <div className="truncate font-medium">{t.title ?? t.domain}</div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="truncate">{t.domain}</span>
                      <Badge variant="outline">{PLACEMENT_CATEGORY_LABEL[t.category]}</Badge>
                      <a href={t.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${t.domain}`}
                        onClick={(e) => e.stopPropagation()}>
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {t.priority_reasons.slice(0, 2).join(" · ")}
                    {t.competitors.length > 0 && (
                      <div className="mt-0.5">On this page: {t.competitors.join(", ")}</div>
                    )}
                  </TableCell>
                  <TableCell><Badge variant="secondary">{PLACEMENT_STATUS_LABEL[t.status]}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <PlacementDetailDialog
        clientId={clientId}
        targetId={selectedId}
        onOpenChange={(open) => !open && setSelectedId(null)}
        onUpdated={replace}
      />
    </Card>
  )
}
