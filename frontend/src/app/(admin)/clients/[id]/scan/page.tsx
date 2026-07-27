// frontend/src/app/clients/[id]/scan/page.tsx
import { getCausality, getClient, getLatestScan, getScanDiff, listRemediation } from "@/lib/api"
import type { CausalityResponse, ScanDiffResponse, RemediationItem, Platform } from "@/types"
import { SCAN_PLATFORMS } from "@/types"
import { ScanClient } from "./ScanClient"
import { RemediationPanel } from "./RemediationPanel"
import { CausalTrendChart } from "@/components/clients/CausalTrendChart"

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
  let causality: CausalityResponse | null = null

  try {
    const [client, scan, diff, items, causal] = await Promise.all([
      getClient(id),
      getLatestScan(id),
      getScanDiff(id),
      listRemediation(id).catch(() => [] as RemediationItem[]),
      getCausality(id).catch(() => null),
    ])
    clientName = client.name
    initialScan = scan
    initialDiff = diff
    remediation = items
    causality = causal
    if (client.enabled_platforms?.length) enabledPlatforms = client.enabled_platforms
  } catch {
    // backend down — show empty state
  }

  const causalPoints = causality?.points ?? []
  const hasControlData = causalPoints.some((p) => p.control_frequency !== null)

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
      {hasControlData && causalPoints.length >= 2 && (
        <section className="space-y-2">
          <h2 className="font-display text-lg font-semibold tracking-tight">
            Proof of impact
          </h2>
          <CausalTrendChart
            dates={causalPoints.map((p) => p.completed_at)}
            optimized={causalPoints.map((p) => p.optimized_frequency)}
            leftAlone={causalPoints.map((p) => p.control_frequency)}
          />
        </section>
      )}
    </div>
  )
}
