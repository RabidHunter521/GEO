// frontend/src/app/clients/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { redirect } from "next/navigation"
import {
  createClient as apiCreateClient,
  updateClient as apiUpdateClient,
  deleteClient as apiDeleteClient,
  addCompetitor as apiAddCompetitor,
  deleteCompetitor as apiDeleteCompetitor,
  createControlQuery as apiCreateControlQuery,
  updateControlQuery as apiUpdateControlQuery,
  createGuarantee as apiCreateGuarantee,
  getGuarantee as apiGetGuarantee,
  resolveGuarantee as apiResolveGuarantee,
  triggerScan as apiTriggerScan,
  generateShareToken as apiGenerateShareToken,
} from "@/lib/api"

export async function createClientAction(data: {
  name: string
  website: string
  industry: string
}) {
  const client = await apiCreateClient(data)
  revalidatePath("/clients")
  return client
}

// Lightweight cold-outreach flow: create the prospect, optionally seed one
// competitor, mint a share link, and kick off a scan in one shot — so the
// prospect view is ready to screen-share in a sales call.
export async function createProspectAction(data: {
  name: string
  website: string
  industry: string
  competitor?: string
}) {
  const client = await apiCreateClient({
    name: data.name,
    website: data.website,
    industry: data.industry,
    is_prospect: true,
    enabled_platforms: ["chatgpt", "perplexity"],
  })
  // Seed the competitor (if given) BEFORE the scan fires so the scan runs its
  // comparison queries — the competitor gap is the centrepiece of the call.
  const competitor = data.competitor?.trim()
  if (competitor) {
    await apiAddCompetitor(client.id, { name: competitor })
  }
  const { share_token } = await apiGenerateShareToken(client.id)
  await apiTriggerScan(client.id)
  revalidatePath("/clients")
  return { client, share_token }
}

export async function triggerScanAction(id: string) {
  await apiTriggerScan(id)
  revalidatePath("/clients")
}

export async function convertProspectToClientAction(id: string) {
  await apiUpdateClient(id, {
    is_prospect: false,
    enabled_platforms: ["chatgpt", "perplexity", "gemini", "claude"],
  })
  revalidatePath("/clients")
}

export async function addCompetitorAction(
  clientId: string,
  data: { name: string; website?: string },
) {
  const comp = await apiAddCompetitor(clientId, data)
  revalidatePath(`/clients/${clientId}`)
  return comp
}

export async function createGuaranteeAction(
  clientId: string,
  data: { metric?: string; target_value: number; deadline_date: string },
) {
  await apiCreateGuarantee(clientId, data)
  revalidatePath(`/clients/${clientId}`)
  // Return the derived progress so the widget can render pace immediately.
  return apiGetGuarantee(clientId)
}

export async function resolveGuaranteeAction(
  clientId: string,
  guaranteeId: string,
  outcome: "met" | "missed" | "void",
  note?: string,
) {
  const g = await apiResolveGuarantee(clientId, guaranteeId, { outcome, note })
  revalidatePath(`/clients/${clientId}`)
  return g
}

export async function addControlQueryAction(
  clientId: string,
  data: { query_text: string; category?: string },
) {
  const cq = await apiCreateControlQuery(clientId, data)
  revalidatePath(`/clients/${clientId}/settings`)
  return cq
}

export async function toggleControlQueryAction(
  clientId: string,
  controlQueryId: string,
  active: boolean,
) {
  const cq = await apiUpdateControlQuery(clientId, controlQueryId, { active })
  revalidatePath(`/clients/${clientId}/settings`)
  return cq
}

export async function deleteCompetitorAction(
  clientId: string,
  competitorId: string,
) {
  await apiDeleteCompetitor(clientId, competitorId)
  revalidatePath(`/clients/${clientId}`)
}

export async function archiveClientAction(id: string) {
  await apiDeleteClient(id)
  revalidatePath("/clients")
  redirect("/clients")
}

export async function archiveClientsAction(ids: string[]) {
  for (const id of ids) {
    await apiDeleteClient(id)
  }
  revalidatePath("/clients")
}

export async function bulkScanAction(
  ids: string[],
): Promise<{ triggered: number; skipped: number }> {
  let triggered = 0
  let skipped = 0
  for (const id of ids) {
    try {
      await apiTriggerScan(id)
      triggered++
    } catch {
      // 409 (scan already running) or any other per-client failure — the rest
      // of the batch still proceeds
      skipped++
    }
  }
  revalidatePath("/clients")
  return { triggered, skipped }
}
