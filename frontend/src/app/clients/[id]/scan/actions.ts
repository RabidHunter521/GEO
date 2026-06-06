"use server"

import { triggerScan, flagHallucination, getLatestScan } from "@/lib/api"
import { revalidatePath } from "next/cache"
import type { Scan } from "@/types"

export async function triggerScanAction(clientId: string): Promise<Scan | null> {
  await triggerScan(clientId)
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
