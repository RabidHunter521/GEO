"use server"

import { ApiError, generateReport, sendReport, getReports } from "@/lib/api"
import { revalidatePath } from "next/cache"
import type { Report } from "@/types"

// Returns the backend's message when the job could not be started, so the UI
// can say "the worker is offline" immediately instead of spinning for 90s and
// then reporting a generic timeout.
export async function triggerGenerateReport(clientId: string): Promise<string | null> {
  try {
    await generateReport(clientId)
  } catch (e) {
    if (e instanceof ApiError && e.status === 503) {
      return e.detail ?? e.message
    }
    throw e
  }
  revalidatePath(`/clients/${clientId}/reports`)
  return null
}

export async function triggerSendReport(clientId: string, reportId: string): Promise<boolean> {
  const result = await sendReport(clientId, reportId)
  revalidatePath(`/clients/${clientId}/reports`)
  return result.sent
}

export async function getReportsAction(clientId: string): Promise<Report[]> {
  return getReports(clientId)
}
