"use server"

import { revalidatePath } from "next/cache"
import {
  generateToolkitFiles as apiGenerate,
  verifyToolkitFiles as apiVerify,
} from "@/lib/api"
import type { ToolkitFiles, VerificationResult } from "@/types"

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
