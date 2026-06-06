// frontend/src/app/clients/[id]/scan/page.tsx
import { getClient, getLatestScan } from "@/lib/api"
import { ScanClient } from "./ScanClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ScanPage({ params }: Props) {
  const { id } = await params
  let clientName = "this client"
  let initialScan = null

  try {
    const [client, scan] = await Promise.all([getClient(id), getLatestScan(id)])
    clientName = client.name
    initialScan = scan
  } catch {
    // backend down — show empty state
  }

  return <ScanClient clientId={id} clientName={clientName} initialScan={initialScan} />
}
