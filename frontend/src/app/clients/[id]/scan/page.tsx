// frontend/src/app/clients/[id]/scan/page.tsx
import { getClient, getLatestScan, getScanDiff } from "@/lib/api"
import type { ScanDiffResponse } from "@/types"
import { ScanClient } from "./ScanClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ScanPage({ params }: Props) {
  const { id } = await params
  let clientName = "this client"
  let initialScan = null
  let initialDiff: ScanDiffResponse | null = null

  try {
    const [client, scan, diff] = await Promise.all([
      getClient(id),
      getLatestScan(id),
      getScanDiff(id),
    ])
    clientName = client.name
    initialScan = scan
    initialDiff = diff
  } catch {
    // backend down — show empty state
  }

  return (
    <ScanClient
      clientId={id}
      clientName={clientName}
      initialScan={initialScan}
      initialDiff={initialDiff}
    />
  )
}
