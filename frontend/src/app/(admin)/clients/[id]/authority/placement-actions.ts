"use server"

import { revalidatePath } from "next/cache"
import {
  ApiError,
  analyzePlacement,
  createPlacementDraft,
  editPlacementDraft,
  getPlacement,
  pursuePlacement,
  setPlacementStatus,
} from "@/lib/api"
import type { PlacementTargetDetail } from "@/types"

export type PlacementResult = { ok: true; detail: PlacementTargetDetail } | { ok: false; error: string }

// Only API errors become a message; anything else (e.g. the session-ended
// redirect apiFetch throws) must propagate untouched.
async function run(clientId: string, fn: () => Promise<PlacementTargetDetail>): Promise<PlacementResult> {
  try {
    const detail = await fn()
    revalidatePath(`/clients/${clientId}/authority`)
    return { ok: true, detail }
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.detail ?? "Request failed. Try again." }
    throw err
  }
}

export async function getPlacementAction(clientId: string, targetId: string) {
  return run(clientId, () => getPlacement(clientId, targetId))
}
export async function analyzePlacementAction(clientId: string, targetId: string) {
  return run(clientId, () => analyzePlacement(clientId, targetId))
}
export async function setPlacementStatusAction(clientId: string, targetId: string, status: "open" | "dismissed") {
  return run(clientId, () => setPlacementStatus(clientId, targetId, status))
}
export async function pursuePlacementAction(clientId: string, targetId: string, dueDate: string | null) {
  return run(clientId, () => pursuePlacement(clientId, targetId, dueDate))
}
export async function createPlacementDraftAction(clientId: string, targetId: string) {
  return run(clientId, () => createPlacementDraft(clientId, targetId))
}
export async function editPlacementDraftAction(
  clientId: string, targetId: string, draftId: string, subject: string, body: string,
) {
  return run(clientId, () => editPlacementDraft(clientId, targetId, draftId, subject, body))
}
