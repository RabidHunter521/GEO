import { getReports } from "@/lib/api"
import type { Report } from "@/types"
import { ReportsClient } from "./ReportsClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ReportsPage({ params }: Props) {
  const { id } = await params
  let reports: Report[] = []
  try {
    reports = await getReports(id)
  } catch {
    // backend down — show empty state
  }
  return <ReportsClient clientId={id} initialReports={reports} />
}
