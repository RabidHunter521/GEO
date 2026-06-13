// frontend/src/components/clients/ClientFilterBar.tsx
// Controlled filter bar for the /clients grid: score band, industry, country
// and last-scan recency. Options are derived from the loaded client list.
"use client"

import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SCORE_BAND_NAMES } from "@/lib/score-utils"
import {
  DEFAULT_FILTERS,
  hasActiveFilters,
  type ClientFilters,
} from "@/lib/client-list-utils"
import type { ClientListItem } from "@/types"

interface Props {
  clients: ClientListItem[]
  filters: ClientFilters
  onChange: (filters: ClientFilters) => void
  visibleCount: number
}

const BAND_LABELS: Record<string, string> = {
  excellent: "Excellent",
  good: "Good",
  fair: "Fair",
  developing: "Developing",
  low: "Low",
}

const RECENCY_OPTIONS = [
  { value: "all", label: "Any time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "never", label: "Never scanned" },
] as const

function uniqueSorted(values: (string | null)[]): string[] {
  return Array.from(new Set(values.filter((v): v is string => !!v))).sort((a, b) =>
    a.localeCompare(b),
  )
}

export function ClientFilterBar({ clients, filters, onChange, visibleCount }: Props) {
  const industries = uniqueSorted(clients.map((c) => c.industry))
  const countries = uniqueSorted(clients.map((c) => c.country))
  const hasUnsetCountry = clients.some((c) => !c.country)

  function set<K extends keyof ClientFilters>(key: K, value: ClientFilters[K]) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <Select value={filters.band} onValueChange={(v) => set("band", v as ClientFilters["band"])}>
        <SelectTrigger className="h-9 w-[150px] text-sm">
          <SelectValue placeholder="Score band" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All scores</SelectItem>
          {SCORE_BAND_NAMES.map((band) => (
            <SelectItem key={band} value={band}>
              {BAND_LABELS[band]}
            </SelectItem>
          ))}
          <SelectItem value="none">No score yet</SelectItem>
        </SelectContent>
      </Select>

      <Select value={filters.industry} onValueChange={(v) => set("industry", v)}>
        <SelectTrigger className="h-9 w-[170px] text-sm">
          <SelectValue placeholder="Industry" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All industries</SelectItem>
          {industries.map((industry) => (
            <SelectItem key={industry} value={industry}>
              {industry}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={filters.country} onValueChange={(v) => set("country", v)}>
        <SelectTrigger className="h-9 w-[160px] text-sm">
          <SelectValue placeholder="Country" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All countries</SelectItem>
          {countries.map((country) => (
            <SelectItem key={country} value={country}>
              {country}
            </SelectItem>
          ))}
          {hasUnsetCountry && <SelectItem value="none">Not set</SelectItem>}
        </SelectContent>
      </Select>

      <Select
        value={filters.recency}
        onValueChange={(v) => set("recency", v as ClientFilters["recency"])}
      >
        <SelectTrigger className="h-9 w-[150px] text-sm">
          <SelectValue placeholder="Last scan" />
        </SelectTrigger>
        <SelectContent>
          {RECENCY_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {hasActiveFilters(filters) && (
        <>
          <Button variant="ghost" size="sm" onClick={() => onChange({ ...DEFAULT_FILTERS })}>
            <X className="mr-1 h-3.5 w-3.5" />
            Clear filters
          </Button>
          <span className="text-xs text-muted-foreground">
            {visibleCount} of {clients.length} client{clients.length !== 1 ? "s" : ""}
          </span>
        </>
      )}
    </div>
  )
}
