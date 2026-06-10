"use server"

import { revalidatePath } from "next/cache"
import { updateActionStatus } from "@/lib/api"

export async function markActionDone(clientId: string, actionId: string): Promise<void> {
  await updateActionStatus(clientId, actionId, "done")
  revalidatePath(`/clients/${clientId}`)
}

export async function markActionDismissed(clientId: string, actionId: string): Promise<void> {
  await updateActionStatus(clientId, actionId, "dismissed")
  revalidatePath(`/clients/${clientId}`)
}
