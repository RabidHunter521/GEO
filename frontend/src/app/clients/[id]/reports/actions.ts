"use server"

import { generateReport, sendReport } from "@/lib/api"
import { revalidatePath } from "next/cache"

export async function triggerGenerateReport(clientId: string) {
  await generateReport(clientId)
  revalidatePath(`/clients/${clientId}/reports`)
}

export async function triggerSendReport(clientId: string, reportId: string) {
  await sendReport(clientId, reportId)
  revalidatePath(`/clients/${clientId}/reports`)
}
