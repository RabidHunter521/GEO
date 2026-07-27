import { getToolkitFiles, getClient, getLatestSiteAudit } from "@/lib/api"
import { ToolkitClient } from "./ToolkitClient"
import { SiteAuditCard } from "@/components/clients/SiteAuditCard"
import type { SiteAuditLatest } from "@/types"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ToolkitPage({ params }: Props) {
  const { id } = await params
  let files = null
  let clientWebsite = ""
  let latestAudit: SiteAuditLatest | null = null
  try {
    const [fetchedFiles, client, fetchedAudit] = await Promise.all([
      getToolkitFiles(id),
      getClient(id),
      getLatestSiteAudit(id).catch(() => null),
    ])
    files = fetchedFiles
    clientWebsite = client.website
    latestAudit = fetchedAudit
  } catch {
    // Backend down or client not found — show empty state
  }
  return (
    <div className="space-y-8">
      <ToolkitClient clientId={id} initialFiles={files} clientWebsite={clientWebsite} />
      <SiteAuditCard clientId={id} initialLatest={latestAudit} />
    </div>
  )
}
