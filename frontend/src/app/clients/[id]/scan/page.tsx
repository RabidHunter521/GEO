// frontend/src/app/clients/[id]/scan/page.tsx
import { getClient, getLatestScan, getScanDiff, listRemediation } from "@/lib/api"
import type { ScanDiffResponse, RemediationItem, Platform } from "@/types"
import { SCAN_PLATFORMS } from "@/types"
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
  let enabledPlatforms: Platform[] = [...SCAN_PLATFORMS]

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
    if (client.enabled_platforms?.length) enabledPlatforms = client.enabled_platforms
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
        enabledPlatforms={enabledPlatforms}
      />
      <RemediationPanel clientId={id} initialItems={remediation} />
    </div>
  )
}
