// frontend/src/app/clients/[id]/scan/page.tsx
import { getClient, getLatestScan, getScanDiff, listRemediation } from "@/lib/api"
import type { ScanDiffResponse, RemediationItem } from "@/types"
import { ScanClient } from "./ScanClient"
import { RemediationPanel } from "./RemediationPanel"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ScanPage({ params }: Props) {
  const { id } = await params
  let clientName = "this client"
  let initialScan = null
  let initialDiff: ScanDiffResponse | null = null
  let remediation: RemediationItem[] = []

  try {
    const [client, scan, diff, items] = await Promise.all([
      getClient(id),
      getLatestScan(id),
      getScanDiff(id),
      listRemediation(id).catch(() => [] as RemediationItem[]),
    ])
    clientName = client.name
    initialScan = scan
    initialDiff = diff
    remediation = items
  } catch {
    // backend down — show empty state
  }

  return (
    <div className="space-y-6">
      <ScanClient
        clientId={id}
        clientName={clientName}
        initialScan={initialScan}
        initialDiff={initialDiff}
      />
      <RemediationPanel clientId={id} initialItems={remediation} />
    </div>
  )
}
