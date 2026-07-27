"use server"

import { revalidatePath } from "next/cache"
import {
  generateToolkitFiles as apiGenerate,
  verifyToolkitFiles as apiVerify,
  generateLlmsFullTxt as apiGenerateLlmsFull,
  runSiteAudit as apiRunSiteAudit,
  getLatestSiteAudit as apiGetLatestSiteAudit,
} from "@/lib/api"
import type { ToolkitFiles, VerificationResult, SiteAuditLatest } from "@/types"

export async function generateToolkitAction(clientId: string): Promise<ToolkitFiles> {
  const files = await apiGenerate(clientId)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return files
}

export async function verifyToolkitAction(clientId: string): Promise<VerificationResult> {
  const result = await apiVerify(clientId)
  revalidatePath(`/clients/${clientId}`)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return result
}

export async function generateLlmsFullAction(clientId: string): Promise<ToolkitFiles> {
  const files = await apiGenerateLlmsFull(clientId)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return files
}

export async function runSiteAuditAction(clientId: string): Promise<SiteAuditLatest | null> {
  await apiRunSiteAudit(clientId)
  // Re-read latest so the response includes the fixed/regressed delta.
  const latest = await apiGetLatestSiteAudit(clientId)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return latest
}
