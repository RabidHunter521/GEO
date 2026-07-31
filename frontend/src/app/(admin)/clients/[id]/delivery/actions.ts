"use server"

import { revalidatePath } from "next/cache"
import { createOutcomeAction, patchOutcomeAction, transitionOutcomeAction } from "@/lib/api"
import type { OutcomeAction, OutcomeActionCreate, OutcomeActionPatch, OutcomeActionStatus } from "@/types"

function revalidateDelivery(clientId: string) {
  revalidatePath(`/clients/${clientId}/delivery`)
  revalidatePath("/review-queue")
}

export async function createOutcomeActionAction(clientId: string, body: OutcomeActionCreate): Promise<OutcomeAction> {
  const action = await createOutcomeAction(clientId, body)
  revalidateDelivery(clientId)
  return action
}

export async function patchOutcomeActionAction(
  clientId: string, actionId: string, body: OutcomeActionPatch,
): Promise<OutcomeAction> {
  const action = await patchOutcomeAction(clientId, actionId, body)
  revalidateDelivery(clientId)
  return action
}

export async function transitionOutcomeActionAction(
  clientId: string, actionId: string, status: OutcomeActionStatus,
): Promise<OutcomeAction> {
  const action = await transitionOutcomeAction(clientId, actionId, status)
  revalidateDelivery(clientId)
  return action
}
