// frontend/src/app/clients/[id]/settings/page.tsx
import { getCurrentAdmin } from "@/lib/current-admin"
import { getAttribution, getClient, getCompetitors, getContentGaps, getControlQueries, getTrafficHistory } from "@/lib/api"
import { SettingsForm } from "./SettingsForm"
import { ShareLinkCard } from "./ShareLinkCard"
import { AttributionCard } from "./AttributionCard"
import { DangerZoneCard } from "./DangerZoneCard"
import { InternalNotesCard } from "@/components/clients/InternalNotesCard"

export default async function SettingsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const admin = await getCurrentAdmin()
  const [client, competitors, trafficHistory, controlQueries] = await Promise.all([
    getClient(id),
    getCompetitors(id),
    getTrafficHistory(id),
    getControlQueries(id),
  ])

  // Content Quality assist — latest crawl-derived recommendation (informational; never auto-scores)
  let contentRecommendation: string | null = null
  try {
    const analysis = await getContentGaps(id)
    contentRecommendation = analysis?.content_quality_recommendation ?? null
  } catch {
    // no analysis yet — hint simply won't show
  }

  // Lead tracking setup — the card simply doesn't render if this fails.
  const attribution = await getAttribution(id).catch(() => null)

  return (
    <div className="max-w-2xl space-y-6">
      <SettingsForm
        client={client}
        competitors={competitors}
        contentRecommendation={contentRecommendation}
        trafficHistory={trafficHistory}
        controlQueries={controlQueries}
      />
      <ShareLinkCard client={client} />
      {attribution && <AttributionCard clientId={client.id} initial={attribution} />}
      <InternalNotesCard
        clientId={client.id}
        initialNotes={client.internal_notes ?? ""}
      />
      {/* Owner-only for clients; any admin may clear out a prospect. */}
      {(admin.isOwner || client.is_prospect) && <DangerZoneCard client={client} />}
    </div>
  )
}
