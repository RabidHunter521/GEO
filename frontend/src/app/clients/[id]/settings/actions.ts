// frontend/src/app/clients/[id]/settings/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { updateClient } from "@/lib/api"

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
    contact_email?: string
    brand_authority_score?: number
    content_quality_score?: number
    score_drop_threshold?: number
  },
) {
  const client = await updateClient(id, data)
  revalidatePath(`/clients/${id}`)
  revalidatePath("/clients")
  return client
}
