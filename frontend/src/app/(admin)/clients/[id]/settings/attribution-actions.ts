"use server"

// Server actions for the lead-source attribution card (AttributionCard.tsx).
import { revalidatePath } from "next/cache"
import {
  ApiError,
  logAttributionAnswer,
  rotateAttributionWebhookSecret,
  updateAttribution,
} from "@/lib/api"
import type { AttributionOverview, AttributionSettingInput, ManualAnswerInput } from "@/types"

function refresh(id: string) {
  revalidatePath(`/clients/${id}`)
  revalidatePath(`/clients/${id}/settings`)
}

// Returns the validation message instead of throwing: production Next.js
// redacts errors thrown from server actions, and "include the country code"
// is exactly what the admin needs to see.
export async function updateAttributionAction(
  id: string,
  body: AttributionSettingInput,
): Promise<{ overview: AttributionOverview } | { error: string }> {
  try {
    const overview = await updateAttribution(id, body)
    refresh(id)
    return { overview }
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) return { error: err.message }
    throw err
  }
}

export async function rotateWebhookSecretAction(id: string) {
  const issued = await rotateAttributionWebhookSecret(id)
  refresh(id)
  return issued
}

export async function logAnswerAction(id: string, body: ManualAnswerInput) {
  const result = await logAttributionAnswer(id, body)
  refresh(id)
  return result
}
