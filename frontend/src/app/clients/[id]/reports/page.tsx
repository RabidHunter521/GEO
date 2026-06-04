import { getReports } from "@/lib/api"
import { ReportsClient } from "./ReportsClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ReportsPage({ params }: Props) {
  const { id } = await params
  let reports = []
  try {
    reports = await getReports(id)
  } catch {
    // backend down — show empty state
  }
  return <ReportsClient clientId={id} initialReports={reports} />
}
