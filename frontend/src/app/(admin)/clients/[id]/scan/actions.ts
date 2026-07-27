"use server"

import {
  ApiError,
  triggerScan,
  flagHallucination,
  getLatestScan,
  syncRemediation,
  updateRemediationStatus,
} from "@/lib/api"
import { revalidatePath } from "next/cache"
import type { Scan, RemediationItem, RemediationStatus } from "@/types"

export async function triggerScanAction(clientId: string): Promise<Scan | null> {
  try {
    await triggerScan(clientId)
  } catch (error) {
    // 409 = a scan is already in progress — fall through and return it so the
    // page simply shows the running scan instead of erroring
    if (!(error instanceof ApiError && error.status === 409)) throw error
  }
  revalidatePath(`/clients/${clientId}/scan`)
  revalidatePath(`/clients/${clientId}`)
  try {
    return await getLatestScan(clientId)
  } catch {
    return null
  }
}

export async function flagHallucinationAction(
  scanId: string,
  resultId: string,
  clientId: string,
): Promise<void> {
  await flagHallucination(scanId, resultId)
  revalidatePath(`/clients/${clientId}/activity`)
}

export async function refreshScanAction(clientId: string): Promise<Scan | null> {
  try {
    return await getLatestScan(clientId)
  } catch {
    return null
  }
}

export async function syncRemediationAction(clientId: string): Promise<RemediationItem[]> {
  const items = await syncRemediation(clientId)
  revalidatePath(`/clients/${clientId}/scan`)
  return items
}

export async function setRemediationStatusAction(
  clientId: string,
  itemId: string,
  status: RemediationStatus,
): Promise<RemediationItem> {
  const item = await updateRemediationStatus(clientId, itemId, status)
  revalidatePath(`/clients/${clientId}/scan`)
  return item
}
