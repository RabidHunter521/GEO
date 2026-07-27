"use server"

import { revalidatePath } from "next/cache"
import {
  runPageAudit,
  getPageAudit,
  generateDeliverable,
  updateDeliverable,
} from "@/lib/api"
import type { ContentDeliverable, DeliverableType, PageAudit } from "@/types"

export async function runPageAuditAction(clientId: string, url: string): Promise<PageAudit> {
  const audit = await runPageAudit(clientId, url)
  revalidatePath(`/clients/${clientId}/content-studio`)
  return audit
}

export async function getPageAuditDetailAction(
  clientId: string,
  auditId: string,
): Promise<PageAudit> {
  return getPageAudit(clientId, auditId)
}

export async function generateDeliverableAction(
  clientId: string,
  type: DeliverableType,
  competitorId?: string,
): Promise<ContentDeliverable> {
  const d = await generateDeliverable(clientId, type, competitorId)
  revalidatePath(`/clients/${clientId}/content-studio`)
  return d
}

export async function updateDeliverableAction(
  clientId: string,
  deliverableId: string,
  patch: { title?: string; body_md?: string; status?: "reviewed" },
): Promise<ContentDeliverable> {
  const d = await updateDeliverable(clientId, deliverableId, patch)
  revalidatePath(`/clients/${clientId}/content-studio`)
  return d
}
