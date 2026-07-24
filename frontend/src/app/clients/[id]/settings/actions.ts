// frontend/src/app/clients/[id]/settings/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { updateClient, upsertTrafficSnapshot, generateShareToken, revokeShareToken, uploadClientLogo, syncGa4Traffic } from "@/lib/api"
import type { Platform } from "@/types"

export async function updateClientAction(
  id: string,
  data: {
    name?: string
    website?: string
    industry?: string
    description?: string
    target_audience?: string
    city?: string
    state?: string
    country?: string
    phone?: string
    contact_email?: string
    logo_url?: string
    brand_authority_score?: number
    brand_authority_evidence?: string
    content_quality_score?: number
    content_quality_evidence?: string
    score_drop_threshold?: number
    scan_cadence_days?: number
    avg_deal_value_rm?: number | null
    visitor_to_lead_pct?: number
    lead_to_customer_pct?: number
    enabled_platforms?: Platform[]
    ga4_property_id?: string | null
  },
) {
  const client = await updateClient(id, data)
  revalidatePath(`/clients/${id}`)
  revalidatePath("/clients")
  return client
}

export async function syncGa4TrafficAction(id: string) {
  const report = await syncGa4Traffic(id)
  revalidatePath(`/clients/${id}`)
  revalidatePath(`/clients/${id}/settings`)
  return report
}

export async function uploadClientLogoAction(id: string, formData: FormData) {
  const client = await uploadClientLogo(id, formData)
  revalidatePath(`/clients/${id}`)
  revalidatePath(`/clients/${id}/settings`)
  return client
}

export async function updateTrafficAction(id: string, period: string, ai_visitors: number) {
  const snapshot = await upsertTrafficSnapshot(id, { period, ai_visitors })
  revalidatePath(`/clients/${id}`)
  revalidatePath(`/clients/${id}/settings`)
  return snapshot
}

export async function generateShareLinkAction(id: string) {
  const token = await generateShareToken(id)
  revalidatePath(`/clients/${id}`)
  revalidatePath(`/clients/${id}/settings`)
  return token
}

export async function revokeShareLinkAction(id: string) {
  await revokeShareToken(id)
  revalidatePath(`/clients/${id}`)
  revalidatePath(`/clients/${id}/settings`)
}

export async function saveInternalNotesAction(clientId: string, notes: string) {
  await updateClient(clientId, { internal_notes: notes })
  revalidatePath(`/clients/${clientId}`)
  revalidatePath(`/clients/${clientId}/settings`)
}
