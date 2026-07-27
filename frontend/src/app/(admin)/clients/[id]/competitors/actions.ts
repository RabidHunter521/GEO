// frontend/src/app/clients/[id]/competitors/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { generateContentBrief, getAIReadiness, runCompetitorSiteAudit } from "@/lib/api"
import type { CompetitorAIReadiness, ContentBrief, CompetitorSiteAudit } from "@/types"

export async function generateBriefAction(
  clientId: string,
  resultId: string,
): Promise<ContentBrief> {
  const brief = await generateContentBrief(clientId, resultId)
  revalidatePath(`/clients/${clientId}/competitors`)
  return brief
}

export async function checkAIReadinessAction(
  clientId: string,
): Promise<CompetitorAIReadiness> {
  return getAIReadiness(clientId)
}

export async function runCompetitorSiteAuditAction(
  clientId: string,
  competitorId: string,
): Promise<CompetitorSiteAudit> {
  return runCompetitorSiteAudit(clientId, competitorId)
}
