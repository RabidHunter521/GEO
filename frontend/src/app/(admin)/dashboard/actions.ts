"use server"
// api.ts is server-only (holds ADMIN_API_KEY); this action is how the client
// component paginates without ever seeing the key.
import { getDashboardFeed } from "@/lib/api"
import type { DashboardFeedResponse, DashboardFilters } from "@/types"

export async function loadMoreFeedAction(
  filters: DashboardFilters,
  offset: number,
): Promise<DashboardFeedResponse> {
  return getDashboardFeed(filters, offset)
}
