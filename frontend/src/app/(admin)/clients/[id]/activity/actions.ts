"use server"

import { revalidatePath } from "next/cache"
import { createWorkLogEntry, patchWorkLogEntry } from "@/lib/api"
import type { WorkLogCategory, WorkLogEntry, WorkLogStatus } from "@/types"

const path = (clientId: string) => `/clients/${clientId}/activity`

export async function createWorkLogAction(
  clientId: string,
  body: { category: WorkLogCategory; description: string; entry_date: string },
): Promise<WorkLogEntry> {
  const entry = await createWorkLogEntry(clientId, body)
  revalidatePath(path(clientId))
  return entry
}

export async function patchWorkLogAction(
  clientId: string,
  entryId: string,
  patch: { description?: string; category?: WorkLogCategory; entry_date?: string; status?: WorkLogStatus },
): Promise<WorkLogEntry> {
  const entry = await patchWorkLogEntry(clientId, entryId, patch)
  revalidatePath(path(clientId))
  return entry
}
