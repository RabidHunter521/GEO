// frontend/src/app/clients/[id]/competitors/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { generateContentBrief } from "@/lib/api"
import type { ContentBrief } from "@/types"

export async function generateBriefAction(
  clientId: string,
  resultId: string,
): Promise<ContentBrief> {
  const brief = await generateContentBrief(clientId, resultId)
  revalidatePath(`/clients/${clientId}/competitors`)
  return brief
}
