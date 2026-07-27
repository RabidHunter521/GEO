"use server"

import { generateReport, sendReport, getReports } from "@/lib/api"
import { revalidatePath } from "next/cache"
import type { Report } from "@/types"

export async function triggerGenerateReport(clientId: string): Promise<void> {
  await generateReport(clientId)
  revalidatePath(`/clients/${clientId}/reports`)
}

export async function triggerSendReport(clientId: string, reportId: string): Promise<boolean> {
  const result = await sendReport(clientId, reportId)
  revalidatePath(`/clients/${clientId}/reports`)
  return result.sent
}

export async function getReportsAction(clientId: string): Promise<Report[]> {
  return getReports(clientId)
}
