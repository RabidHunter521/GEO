"use server"

import { revalidatePath } from "next/cache"
import { runContentAnalysis as apiAnalyze, getContentGaps } from "@/lib/api"
import type { ContentAnalysis } from "@/types"

export async function runContentAnalysisAction(clientId: string): Promise<ContentAnalysis> {
  const analysis = await apiAnalyze(clientId)
  revalidatePath(`/clients/${clientId}/content-gaps`)
  revalidatePath(`/clients/${clientId}/settings`)
  return analysis
}

export async function refreshContentGapsAction(clientId: string): Promise<ContentAnalysis | null> {
  try {
    return await getContentGaps(clientId)
  } catch {
    return null
  }
}
