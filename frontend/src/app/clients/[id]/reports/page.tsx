import { getReports, getClient } from "@/lib/api"
import type { Report } from "@/types"
import { ReportsClient } from "./ReportsClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ReportsPage({ params }: Props) {
  const { id } = await params
  let reports: Report[] = []
  let contactEmail: string | null = null
  try {
    const [fetchedReports, client] = await Promise.all([getReports(id), getClient(id)])
    reports = fetchedReports
    contactEmail = client.contact_email ?? null
  } catch {
    // backend down — show empty state
  }
  return <ReportsClient clientId={id} initialReports={reports} contactEmail={contactEmail} />
}
