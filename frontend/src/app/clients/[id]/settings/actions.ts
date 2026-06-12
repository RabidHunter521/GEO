// frontend/src/app/clients/[id]/settings/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { updateClient, upsertTrafficSnapshot, generateShareToken, revokeShareToken } from "@/lib/api"

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
    contact_email?: string
    brand_authority_score?: number
    brand_authority_evidence?: string
    content_quality_score?: number
    content_quality_evidence?: string
    score_drop_threshold?: number
  },
) {
  const client = await updateClient(id, data)
  revalidatePath(`/clients/${id}`)
  revalidatePath("/clients")
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
