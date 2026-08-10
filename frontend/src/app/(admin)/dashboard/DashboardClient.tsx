"use client"

import { useState, useTransition } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { AlertTriangle, ArrowDownRight, ArrowUpRight, DollarSign } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SearchableSelect } from "@/components/ui/searchable-select"
import { presentActivityNote, presentActivityType } from "@/lib/activity-presentation"
import { PRODUCT_LANGUAGE } from "@/lib/product-language"
import { getScoreColor } from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type {
  DashboardEventTier,
  DashboardFeedItem,
  DashboardFeedResponse,
  DashboardFilters,
  DashboardSummary,
} from "@/types"
import { loadMoreFeedAction } from "./actions"

const ALL_CLIENTS = "All clients"

const CATEGORY_OPTIONS = [
  { value: "scans", label: "Scans" },
  { value: "reports_emails", label: "Reports & Emails" },
  { value: "alerts_issues", label: "Alerts & Issues" },
  { value: "content_work", label: "Content Work" },
  { value: "admin", label: "Admin" },
] as const

const TIER_ROW_STYLES: Record<DashboardEventTier, string> = {
  attention: "border-l-2 border-l-destructive",
  notable: "",
  routine: "opacity-70",
}

const TIER_BADGE_VARIANT: Record<
  DashboardEventTier,
  "destructive" | "secondary" | "outline"
> = {
  attention: "destructive",
  notable: "secondary",
  routine: "outline",
}

const SCORE_TEXT: Record<ReturnType<typeof getScoreColor>, string> = {
  green: "text-emerald-600",
  yellow: "text-amber-600",
  red: "text-red-600",
}

// Backend timestamps are naive UTC with no zone suffix; without the "Z" the
// browser would parse them as local time and shift everything by +8h.
function formatUtc(ts: string): string {
  const iso = ts.endsWith("Z") || ts.includes("+") ? ts : `${ts}Z`
  return new Intl.DateTimeFormat("en-MY", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso))
}

function usd(n: number): string {
  return `$${n.toFixed(2)}`
}

interface Props {
  filters: DashboardFilters
  summary: DashboardSummary
  initialFeed: DashboardFeedResponse
  clients: { id: string; name: string }[]
}

export function DashboardClient({ filters, summary, initialFeed, clients }: Props) {
  const router = useRouter()
  const [items, setItems] = useState<DashboardFeedItem[]>(initialFeed.items)
  const [hasMore, setHasMore] = useState(initialFeed.has_more)
  const [customOpen, setCustomOpen] = useState(Boolean(filters.startDate))
  const [customStart, setCustomStart] = useState(filters.startDate ?? "")
  const [customEnd, setCustomEnd] = useState(filters.endDate ?? "")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function push(next: DashboardFilters) {
    const p = new URLSearchParams()
    if (next.startDate && next.endDate) {
      p.set("start", next.startDate)
      p.set("end", next.endDate)
    } else if (next.days && next.days !== 30) {
      p.set("days", String(next.days))
    }
    if (next.clientId) p.set("client", next.clientId)
    if (next.category) p.set("category", next.category)
    if (next.eventType) p.set("event", next.eventType)
    if (next.attentionOnly) p.set("attention", "1")
    const qs = p.toString()
    startTransition(() => router.push(qs ? `/dashboard?${qs}` : "/dashboard"))
  }

  function onPeriodChange(value: string) {
    if (value === "custom") {
      setCustomOpen(true)
      return
    }
    setCustomOpen(false)
    push({ ...filters, days: Number(value), startDate: undefined, endDate: undefined })
  }

  function applyCustomRange() {
    if (!customStart || !customEnd || customEnd < customStart) return
    push({ ...filters, startDate: customStart, endDate: customEnd })
  }

  function onClientChange(name: string) {
    const client = clients.find((c) => c.name === name)
    push({ ...filters, clientId: client?.id })
  }

  async function loadMore() {
    setLoadError(null)
    try {
      const next = await loadMoreFeedAction(filters, items.length)
      setItems((prev) => [...prev, ...next.items])
      setHasMore(next.has_more)
    } catch {
      setLoadError("Could not load more events. Try again.")
    }
  }

  // Tile links preserve the current period/client, swap the feed slice.
  function eventFilterHref(eventType: string): string {
    const p = new URLSearchParams()
    if (filters.startDate && filters.endDate) {
      p.set("start", filters.startDate)
      p.set("end", filters.endDate)
    } else if (filters.days && filters.days !== 30) {
      p.set("days", String(filters.days))
    }
    if (filters.clientId) p.set("client", filters.clientId)
    p.set("event", eventType)
    return `/dashboard?${p.toString()}`
  }

  const selectedClientName =
    clients.find((c) => c.id === filters.clientId)?.name ?? ALL_CLIENTS
  const periodValue = filters.startDate ? "custom" : String(filters.days ?? 30)
  const { attention, portfolio, cost } = summary

  const attentionRows: { label: string; count: number; event: string }[] = [
    { label: "Scans failed", count: attention.scans_failed, event: "scan_failed" },
    { label: "Platforms unavailable", count: attention.platforms_unavailable, event: "scan_platform_unavailable" },
    { label: "Accuracy issues", count: attention.hallucinations_flagged, event: "hallucination_flagged" },
    { label: "Alerts sent", count: attention.alerts_sent, event: "alert_sent" },
    { label: "Share-of-source changes", count: attention.share_of_source_changes, event: "citation_flip" },
  ]
  const totalAttention = attentionRows.reduce((sum, r) => sum + r.count, 0)

  return (
    <div className={cn("space-y-6", isPending && "pointer-events-none opacity-60")}>
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everything happening across your clients. Filters drive the whole page.
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-40">
          <Select value={periodValue} onValueChange={onPeriodChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
              <SelectItem value="custom">Custom range</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {customOpen && (
          <div className="flex items-end gap-2">
            <Input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="w-40"
              aria-label="Start date"
            />
            <Input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="w-40"
              aria-label="End date"
            />
            <Button variant="secondary" size="sm" onClick={applyCustomRange}>
              Apply
            </Button>
          </div>
        )}
        <div className="w-56">
          <SearchableSelect
            options={[ALL_CLIENTS, ...clients.map((c) => c.name)]}
            value={selectedClientName}
            onChange={onClientChange}
          />
        </div>
        <div className="w-48">
          <Select
            value={filters.category ?? "all"}
            onValueChange={(v) =>
              push({ ...filters, category: v === "all" ? undefined : v, eventType: undefined })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {CATEGORY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          variant={filters.attentionOnly ? "default" : "outline"}
          size="sm"
          onClick={() => push({ ...filters, attentionOnly: !filters.attentionOnly })}
        >
          <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
          Attention only
        </Button>
        {filters.eventType && (
          <Badge variant="secondary" className="gap-1">
            {presentActivityType(filters.eventType).label}
            <button
              aria-label="Clear event filter"
              onClick={() => push({ ...filters, eventType: undefined })}
              className="ml-1 font-bold"
            >
              ×
            </button>
          </Badge>
        )}
      </div>

      {/* Stats strip */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Needs attention
            </CardTitle>
          </CardHeader>
          <CardContent>
            {totalAttention === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing needs attention in this period.</p>
            ) : (
              <ul className="space-y-1">
                {attentionRows
                  .filter((r) => r.count > 0)
                  .map((r) => (
                    <li key={r.event}>
                      <Link
                        href={eventFilterHref(r.event)}
                        className="flex items-center justify-between text-sm hover:underline"
                      >
                        <span>{r.label}</span>
                        <span className="font-semibold text-destructive">{r.count}</span>
                      </Link>
                    </li>
                  ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Portfolio health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {portfolio.average_score === null ? (
              <p className="text-sm text-muted-foreground">No scans in this period yet.</p>
            ) : (
              <>
                <p className="text-2xl font-bold">
                  <span className={SCORE_TEXT[getScoreColor(portfolio.average_score)]}>
                    {portfolio.average_score}
                  </span>{" "}
                  <span className="text-sm font-normal text-muted-foreground">
                    avg {PRODUCT_LANGUAGE.readiness} · {portfolio.clients_scored} client
                    {portfolio.clients_scored === 1 ? "" : "s"}
                  </span>
                </p>
                {portfolio.average_delta !== null && (
                  <p className="text-sm text-muted-foreground">
                    {portfolio.average_delta >= 0 ? "+" : ""}
                    {portfolio.average_delta} avg movement this period
                  </p>
                )}
                {portfolio.biggest_gainer && (
                  <p className="flex items-center gap-1 text-sm">
                    <ArrowUpRight className="h-3.5 w-3.5 text-emerald-600" />
                    <Link href={`/clients/${portfolio.biggest_gainer.client_id}`} className="hover:underline">
                      {portfolio.biggest_gainer.client_name}
                    </Link>
                    <span className="text-emerald-600">+{portfolio.biggest_gainer.delta}</span>
                  </p>
                )}
                {portfolio.biggest_decliner && (
                  <p className="flex items-center gap-1 text-sm">
                    <ArrowDownRight className="h-3.5 w-3.5 text-red-600" />
                    <Link href={`/clients/${portfolio.biggest_decliner.client_id}`} className="hover:underline">
                      {portfolio.biggest_decliner.client_name}
                    </Link>
                    <span className="text-red-600">{portfolio.biggest_decliner.delta}</span>
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              LLM cost
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <p className="flex items-center gap-1 text-2xl font-bold">
              <DollarSign className="h-5 w-5 text-muted-foreground" />
              {usd(cost.total_cost_usd)}
            </p>
            {cost.top_service && (
              <p className="text-sm text-muted-foreground">
                Top service: {cost.top_service.service} ({usd(cost.top_service.cost_usd)})
              </p>
            )}
            {cost.selected_client_cost_usd !== null && (
              <p className="text-sm text-muted-foreground">
                {selectedClientName}: {usd(cost.selected_client_cost_usd)}
              </p>
            )}
            {cost.unattributed_cost_usd > 0 && (
              <p className="text-sm text-muted-foreground">
                Unattributed: {usd(cost.unattributed_cost_usd)}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Feed */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Activity ({initialFeed.total})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No events match these filters.
            </p>
          ) : (
            <ul className="divide-y divide-border/60">
              {items.map((item) => (
                <li key={item.id}>
                  <Link
                    href={item.link_path}
                    className={cn(
                      "flex items-start gap-3 px-2 py-2.5 transition-colors hover:bg-accent/50",
                      TIER_ROW_STYLES[item.tier],
                    )}
                  >
                    <Badge variant={TIER_BADGE_VARIANT[item.tier]} className="mt-0.5 shrink-0">
                      {presentActivityType(item.event_type).label}
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{presentActivityNote(item.note)}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {item.client_name} · {formatUtc(item.created_at)}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {loadError && <p className="mt-3 text-sm text-destructive">{loadError}</p>}
          {hasMore && (
            <div className="mt-4 text-center">
              <Button variant="outline" size="sm" onClick={loadMore}>
                Load more
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
