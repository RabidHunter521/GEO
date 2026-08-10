// frontend/src/app/(admin)/dashboard/page.tsx
// Global dashboard — everything happening across the agency. Server
// component: filters live in the URL so views are bookmarkable and the
// data fetch happens server-side (api.ts is server-only).
import { getClients, getDashboardFeed, getDashboardSummary } from "@/lib/api"
import type { DashboardFilters } from "@/types"
import { DashboardClient } from "./DashboardClient"

export const dynamic = "force-dynamic"

type SearchParams = Record<string, string | string[] | undefined>

function parseFilters(sp: SearchParams): DashboardFilters {
  const s = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : undefined)
  const rawDays = Number(s("days") ?? "30")
  return {
    days: Number.isInteger(rawDays) && rawDays >= 1 && rawDays <= 365 ? rawDays : 30,
    startDate: s("start"),
    endDate: s("end"),
    clientId: s("client"),
    category: s("category"),
    eventType: s("event"),
    attentionOnly: s("attention") === "1",
  }
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams
  const filters = parseFilters(sp)
  const [summary, feed, clients] = await Promise.all([
    getDashboardSummary(filters),
    getDashboardFeed(filters),
    getClients(),
  ])
  return (
    <DashboardClient
      // Remount on any filter change so feed pagination state resets.
      key={JSON.stringify(filters)}
      filters={filters}
      summary={summary}
      initialFeed={feed}
      clients={clients.map((c) => ({ id: c.id, name: c.name }))}
    />
  )
}
