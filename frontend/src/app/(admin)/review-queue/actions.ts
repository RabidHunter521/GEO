"use server"

import { revalidatePath } from "next/cache"
import { patchWorkLogEntry } from "@/lib/api"
import type { WorkLogEntry, WorkLogStatus } from "@/types"

// Publish/dismiss reuse the per-client PATCH — the only write path into this
// table. Revalidate both the queue and the client's own activity page, since
// the entry appears on both.
export async function reviewWorkLogAction(
  clientId: string,
  entryId: string,
  patch: { description?: string; status?: WorkLogStatus },
): Promise<WorkLogEntry> {
  const entry = await patchWorkLogEntry(clientId, entryId, patch)
  revalidatePath("/review-queue")
  revalidatePath(`/clients/${clientId}/activity`)
  return entry
}
