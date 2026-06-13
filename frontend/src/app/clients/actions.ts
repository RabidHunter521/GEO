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

// Lightweight cold-outreach flow: create the prospect, mint a share link, and
// kick off a scan in one shot so the partner walks away with a sendable link.
export async function createProspectAction(data: {
  name: string
  website: string
  industry: string
}) {
  const client = await apiCreateClient({ ...data, is_prospect: true })
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
  await apiUpdateClient(id, { is_prospect: false })
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
